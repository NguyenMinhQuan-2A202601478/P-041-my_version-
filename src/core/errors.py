"""Custom exceptions va exception handlers cho FastAPI.

Vi sao can lop nay? Thay vi rai `raise HTTPException(status_code=404, ...)`
khap noi trong code (kho doc, de go sai status code), ta dinh nghia cac
exception co TEN RO RANG (NotFoundException, ForbiddenException...) — code
goi noi doc len la hieu ngay y nghia. `register_exception_handlers()` dang
ky 1 noi duy nhat de moi exception nay deu tra ve JSON dung 1 format nhat
quan, dung theo API Contract: `{"detail": "...", "status_code": ...}`.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Lop co so cho moi loi nghiep vu (business error) cua ung dung.

    Ten lop ket thuc bang "Error" (khong phai "Exception") de tuan thu quy
    uoc dat ten cua ruff (rule N818). Cac lop con ben duoi (NotFoundException,
    ForbiddenException, ValidationException) giu nguyen ten "*Exception" theo
    yeu cau cua API Contract — ruff chi kiem tra lop nao ke thua truc tiep
    tu `Exception`, nen chi lop co so nay can doi ten.
    """

    status_code: int = 400

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class NotFoundException(AppError):  # noqa: N818 - ten giu theo API Contract da duyet
    """Khong tim thay tai nguyen (vd: CV, JD, phien phong van khong ton tai)."""

    status_code = 404


class ForbiddenException(AppError):  # noqa: N818 - ten giu theo API Contract da duyet
    """Nguoi dung khong co quyen thuc hien hanh dong nay (vi pham phan quyen)."""

    status_code = 403


class ValidationException(AppError):  # noqa: N818 - ten giu theo API Contract da duyet
    """Du lieu dau vao khong hop le nhung khong duoc Pydantic bat tu dong."""

    status_code = 422


def register_exception_handlers(app: FastAPI) -> None:
    """Dang ky handler chung cho moi `AppError` (va cac lop con cua no).

    Goi ham nay 1 lan khi khoi tao app (xem src/main.py).
    """

    @app.exception_handler(AppError)
    async def app_exception_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "status_code": exc.status_code},
        )
