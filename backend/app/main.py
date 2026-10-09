"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .api import routes
from .config import get_settings
from .db import init_db
from .services.state import get_state

log = logging.getLogger("fin04")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    st = get_state()
    init_db(st.dataset.scenarios)
    log.info("startup complete")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="FIN-04 Climate Exposure Graph API", version=__version__, lifespan=lifespan,
                  description="Food & Beverage supply-chain climate stress testing on a SYNTHETIC demonstration dataset. "
                              "Outputs are model estimates under stated assumptions, not forecasts.")
    app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_list, allow_methods=["*"], allow_headers=["*"])
    for r in (routes.system, routes.graph, routes.scen, routes.ana, routes.mit, routes.dat):
        app.include_router(r)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(status_code=500, content={"detail": "internal error; see server logs"})

    return app


app = create_app()
