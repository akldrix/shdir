import argparse

import qrcode

from .utils.colors import GREEN, RESET, UNDERLINE
from .utils.logs import logger
from .utils.net import get_local_ip

parser = argparse.ArgumentParser(description="Shdir file manager")
parser.add_argument(
    "--code",
    "-c",
    type=str,
    default=None,
    help="Access code for current session",
)

parser.add_argument(
    "--auth",
    "-a",
    action="store_true",
    help="Run server with authentication",
)
parser.add_argument(
    "--https",
    action="store_true",
    help="Run server with temporary tsl certificate",
)
parser.add_argument(
    "--dir",
    "-d",
    type=str,
    default=None,
    help="Set up a directory to share",
)
parser.add_argument(
    "--no-upload",
    "-u",
    action="store_true",
    help="Run without file upload",
)
parser.add_argument(
    "--port",
    "-p",
    type=int,
    default=8000,
    help="Set the port to run server on (default: %(default)s)",
)
args, _ = parser.parse_known_args()
PORT = 8000
if args.port:
    PORT = args.port


def make_qr():
    is_https = args.https
    qr = qrcode.QRCode(version=1, box_size=1, border=1)

    if is_https:
        qr.add_data(f"https://{get_local_ip()}:{PORT}/")

        logger.info(
            f"\n{UNDERLINE}{GREEN} Copy Link: https://{get_local_ip()}:{PORT}/{RESET}\n\n"
        )
    else:
        qr.add_data(f"http://{get_local_ip()}:{PORT}/")
        logger.info(
            f"\n{UNDERLINE}{GREEN} Copy Link: http://{get_local_ip()}:{PORT}/{RESET}\n\n"
        )
    qr.make(fit=True)

    matrix = qr.get_matrix()

    WHITE_BLOCK = "\033[7m  \033[m"
    BLACK_BLOCK = "  "

    indent = "  "

    qr_lines = []
    for row in matrix:
        line = "".join(BLACK_BLOCK if cell else WHITE_BLOCK for cell in row)
        qr_lines.append(f"{indent}{line}")

    tabulated_qr = "\n".join(qr_lines)

    logger.info(f"{tabulated_qr}")
