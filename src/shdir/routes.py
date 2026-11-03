from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.params import Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_async_session
from .models import Chat, Message
from .utils.security import check_authenticated

router = APIRouter(tags=["Chats"])
BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=BASE_DIR / "templates")


@router.get("/chat", response_class=HTMLResponse)
async def get_chats(
    request: Request, session: Annotated[AsyncSession, Depends(get_async_session)]
):
    try:
        check_authenticated(request)
    except HTTPException as e:
        if e.status_code == 401:
            return RedirectResponse(url="/login", status_code=303)
        raise e

    query = select(Chat)
    result = await session.execute(query)
    chats = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="chats.html",
        context={
            "chats": chats,
        },
    )


@router.post("/chat", response_class=HTMLResponse)
async def create_chat(
    request: Request,
    name: Annotated[str, Form()],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    try:
        check_authenticated(request)
    except HTTPException as e:
        if e.status_code == 401:
            return RedirectResponse(url="/login", status_code=303)
        raise e

    new_chat = Chat(name=name)
    session.add(new_chat)
    await session.commit()

    return RedirectResponse(url="/chat", status_code=303)


@router.get("/chat/{chat_id}", response_class=HTMLResponse)
async def get_chat_messages(
    request: Request,
    chat_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    try:
        check_authenticated(request)
    except HTTPException as e:
        if e.status_code == 401:
            return RedirectResponse(url="/login", status_code=303)
        raise e

    query = (
        select(Message).filter(Message.chat_id == chat_id).order_by(Message.id.desc())
    )
    result = await session.execute(query)
    messages = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="messages.html",
        context={
            "messages": messages,
            "chat_id": chat_id,
        },
    )


@router.post("/chat/{chat_id}", response_class=RedirectResponse)
async def send_message(
    request: Request,
    chat_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    text: Annotated[str, Form()],
):
    try:
        check_authenticated(request)
    except HTTPException as e:
        if e.status_code == 401:
            return RedirectResponse(url="/login", status_code=303)
        raise e

    new_message = Message(
        chat_id=chat_id,
        text=text,
    )
    session.add(new_message)
    await session.commit()

    return RedirectResponse(url=f"/chat/{chat_id}", status_code=303)


@router.delete("/chat/{chat_id}/messages/{message_id}", status_code=204)
async def delete_message(
    request: Request,
    chat_id: int,
    message_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    try:
        check_authenticated(request)
    except HTTPException as e:
        if e.status_code == 401:
            return RedirectResponse(url="/login", status_code=303)
        raise e

    query = select(Message).where(Message.chat_id == chat_id, Message.id == message_id)

    result = await session.execute(query)
    message = result.scalar_one_or_none()

    await session.delete(message)
    await session.commit()

    return Response(status_code=204)


@router.delete("/chat/{chat_id}", status_code=204)
async def delete_chat(
    request: Request,
    chat_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    try:
        check_authenticated(request)
    except HTTPException as e:
        if e.status_code == 401:
            return RedirectResponse(url="/login", status_code=303)
        raise e

    query = select(Chat).where(Chat.id == chat_id)

    result = await session.execute(query)
    chat = result.scalar_one_or_none()

    await session.delete(chat)
    await session.commit()

    return Response(status_code=204)


@router.put("/chat/{chat_id}/messages/{message_id}", status_code=200)
async def update_message(
    request: Request,
    chat_id: int,
    message_id: int,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    text: Annotated[str, Form()],
):
    try:
        check_authenticated(request)
    except HTTPException as e:
        if e.status_code == 401:
            return RedirectResponse(url="/login", status_code=303)
        raise e

    query = select(Message).filter(Message.chat_id == chat_id, Message.id == message_id)
    result = await session.execute(query)
    if not result:
        raise HTTPException(status_code=404, detail="Message not found")
    message = result.scalars().one()
    message.text = text

    await session.commit()
    await session.refresh(message)

    return message
