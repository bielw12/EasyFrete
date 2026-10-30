from fastapi import APIRouter, Request

from app.ui import render

router = APIRouter()


@router.get("/")
def inicio(request: Request):
    return render(request, "em_construcao.html", titulo="Painel")
