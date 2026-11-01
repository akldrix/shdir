import secrets
import shutil
import urllib
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import (
    FastAPI,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from zipstream import ZipStream

from .cli import args, make_qr
from .utils.colors import BLUE, CYAN, RESET
from .utils.logs import log_config, logger
from .utils.security import temp_tls_cert

COOKIE_NAME = "shdir_session"
SERVER_CODE: str | None = None
IS_AUTH_ENABLED = args.auth
IS_HTTPS_ENABLED = args.https
IS_UPLOAD_DISABLED = args.no_upload
if args.dir:
    dir_path = Path(args.dir)
    if dir_path.is_dir():
        BASE_DIR = dir_path.resolve()
    else:
        raise NotADirectoryError(
            f"This path is not a dir or does not exist: {dir_path}"
        )
else:
    BASE_DIR = Path.cwd().resolve()


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"


if args.code:
    IS_AUTH_ENABLED = True
    SERVER_CODE = args.code
elif IS_AUTH_ENABLED:
    SERVER_CODE = "".join(secrets.choice("0123456789") for _ in range(6))


def check_authenticated(request: Request):
    if IS_AUTH_ENABLED:
        session_token = request.cookies.get(COOKIE_NAME)

        if not session_token or not secrets.compare_digest(session_token, SERVER_CODE):
            raise HTTPException(status_code=401, detail="Not authenticated")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"\n{CYAN} Sharing Directory: {BASE_DIR}{RESET}")

    if IS_AUTH_ENABLED and SERVER_CODE is not None:
        logger.info(f"\n{BLUE} ACCESS CODE: {SERVER_CODE}{RESET}")

    make_qr()
    logger.info(f"\n{BLUE} Server is running. Press Ctrl + C to stop...{RESET}\n")
    yield


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATE_DIR)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if IS_AUTH_ENABLED and request.cookies.get(COOKIE_NAME) == SERVER_CODE:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(request=request, name="login-page.html")


@app.post("/login")
async def login_process(request: Request, code: str = Form(...)):

    if secrets.compare_digest(code, SERVER_CODE):
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            key=COOKIE_NAME,
            value=SERVER_CODE,
            httponly=True,
            samesite="lax",
        )
        return response
    return templates.TemplateResponse(
        request=request,
        name="login-page.html",
        context={"error": True},
        status_code=401,
    )


@app.get("/", response_class=HTMLResponse)
@app.get("/{subpath:path}", response_class=HTMLResponse)
async def get_files_page(request: Request, subpath: str = ""):
    try:
        check_authenticated(request)
    except HTTPException as e:
        if e.status_code == 401:
            return RedirectResponse(url="/login", status_code=303)
        raise e

    zip_target = request.query_params.get("zip")
    if zip_target:
        target_path = (BASE_DIR / zip_target).resolve()

        if (
            not target_path.is_relative_to(BASE_DIR)
            or not target_path.exists()
            or not target_path.is_dir()
        ):
            raise HTTPException(
                status_code=403, detail="Access denied or invalid directory"
            )

        zs = ZipStream.from_path(str(target_path))

        archive_filename = f"{target_path.name or 'root'}.zip"

        encoded_filename = urllib.parse.quote(archive_filename)

        return StreamingResponse(
            zs,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            },
        )

    media_target = request.query_params.get("media")

    if media_target:
        target_path = (BASE_DIR / media_target).resolve()

        if (
            not target_path.is_relative_to(BASE_DIR)
            or not target_path.exists()
            or not target_path.is_file()
        ):
            raise HTTPException(status_code=403, detail="Access denied or invalid file")
        return FileResponse(
            path=target_path,
            # media_type="video/mp4",
            headers={"Content-Disposition": "inline"},
        )

    target_path = (BASE_DIR / subpath).resolve()

    if not target_path.is_relative_to(BASE_DIR):
        raise HTTPException(status_code=403, detail="Access denied")
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    if target_path.is_file():
        return FileResponse(
            path=target_path,
            filename=target_path.name,
            media_type="application/octet-stream",
        )
    if target_path != BASE_DIR:
        parent_rel = target_path.parent.relative_to(BASE_DIR)
        parent_path = (
            str(parent_rel).replace("\\", "/") if str(parent_rel) != "." else ""
        )
    else:
        parent_path = ""

    dirs = []
    files = []

    for path in target_path.iterdir():
        rel_path = path.relative_to(BASE_DIR)
        web_rel_path = str(rel_path).replace("\\", "/")

        if path.is_dir():
            dirs.append(
                {
                    "name": path.name,
                    "path": web_rel_path,
                }
            )
        elif path.is_file():
            files.append(
                {
                    "name": path.name,
                    "path": web_rel_path,
                    "ext": path.suffix,
                }
            )
    path_len = [p for p in subpath.split("/") if p]
    depth = len(path_len)
    context = {
        "files": files,
        "dirs": dirs,
        "subpath": subpath,
        "parent_path": parent_path,
        "is_root": target_path == BASE_DIR,
        "root": "",
        "show_home": depth >= 2,
        "upload": not IS_UPLOAD_DISABLED,
    }

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=context,
    )


@app.post("/")
@app.post("/{subpath:path}")
async def upload_file(
    request: Request,
    files: list[UploadFile],
    subpath: str = "",
):
    if not IS_UPLOAD_DISABLED:
        try:
            check_authenticated(request)
        except HTTPException as e:
            if e.status_code == 401:
                return RedirectResponse(url="/login", status_code=303)
            raise e

        target_path = (BASE_DIR / subpath).resolve()

        if not target_path.is_relative_to(BASE_DIR):
            raise HTTPException(status_code=403, detail="Access denied")
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="Not found")
        for file in files:
            if not file.filename:
                continue

            dest_path = target_path / file.filename

            try:
                with dest_path.open("wb") as buf:
                    shutil.copyfileobj(file.file, buf)
            except Exception as e:
                logger.error(f"Error occured while loading file: {e}")
                raise HTTPException(status_code=500, detail="Could not save file")
            finally:
                await file.close()

        return RedirectResponse(url=request.url.path, status_code=303)


def run_app():
    if IS_HTTPS_ENABLED:
        with temp_tls_cert() as (cert_path, key_path):
            uvicorn.run(
                "src.shdir.app:app",
                host="0.0.0.0",
                port=8000,
                reload=False,
                log_config=log_config,
                ssl_certfile=cert_path,
                ssl_keyfile=key_path,
            )
    else:
        uvicorn.run(
            "src.shdir.app:app",
            host="0.0.0.0",
            port=8000,
            reload=False,
            log_config=log_config,
        )


if __name__ == "__main__":
    run_app()
