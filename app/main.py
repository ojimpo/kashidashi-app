from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import Generator
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .database import create_engine_for_url, create_session_factory, init_database
from .domain import ItemSort, ItemStatus, ItemType
from .schemas import ItemCreate, ItemRead, ItemUpdate
from .services import create_item, delete_item, get_item_or_404, list_items, update_item
from .settings import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()
    static_dir = Path(__file__).resolve().parent / "static"
    engine = create_engine_for_url(resolved_settings.database_url)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> object:
        init_database(app.state.engine)
        yield
        app.state.engine.dispose()

    app = FastAPI(
        title=resolved_settings.app_name,
        description=(
            "図書館貸出資料を記録・管理する API です。"
            " UI からの操作だけでなく、OpenClaw などの外部エージェントによる自動登録・"
            " リッピング完了記録・返却記録の連携を想定しています。"
        ),
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.settings = resolved_settings

    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    router = APIRouter(prefix="/api/items", tags=["items"])

    def get_session(request: Request) -> Generator[Session, None, None]:
        session = request.app.state.session_factory()
        try:
            yield session
        finally:
            session.close()

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @router.get(
        "",
        response_model=list[ItemRead],
        summary="資料一覧を取得する",
        description=(
            "一覧表示や外部エージェントによる巡回処理で使う取得 API です。"
            " 例: `type=cd&status=not_ripped` で未リッピング CD を取得します。"
        ),
    )
    def list_items_endpoint(
        session: Session = Depends(get_session),
        item_type: ItemType | None = Query(default=None, alias="type"),
        status_filter: ItemStatus | None = Query(default=None, alias="status"),
        library: str | None = None,
        artist: str | None = None,
        author: str | None = None,
        sort: ItemSort = ItemSort.BORROWED_DATE_DESC,
    ) -> list[ItemRead]:
        return list_items(
            session,
            item_type=item_type,
            status_filter=status_filter,
            library=library,
            artist=artist,
            author=author,
            sort=sort,
        )

    @router.post(
        "",
        response_model=ItemRead,
        status_code=status.HTTP_201_CREATED,
        summary="資料を登録する",
        description=(
            "新規貸出時に図書館サイトから取得した情報を登録します。"
            " library 省略時は既定の図書館名を使用し、"
            " title + artist/author + borrowed_date の重複は 409 で拒否します。"
        ),
    )
    def create_item_endpoint(payload: ItemCreate, session: Session = Depends(get_session)) -> ItemRead:
        return create_item(session, payload)

    @router.get(
        "/{item_id}",
        response_model=ItemRead,
        summary="資料詳細を取得する",
        description="単一資料の詳細表示や編集前の読み込みに使います。",
    )
    def get_item_endpoint(item_id: int, session: Session = Depends(get_session)) -> ItemRead:
        return get_item_or_404(session, item_id)

    @router.patch(
        "/{item_id}",
        response_model=ItemRead,
        summary="資料を更新する",
        description=(
            "資料情報の部分更新 API です。"
            " リッピング完了時は `ripped_at` や MusicBrainz 情報を、"
            " 返却時は `returned_at` をこの API で記録します。"
        ),
    )
    def update_item_endpoint(
        item_id: int,
        payload: ItemUpdate,
        session: Session = Depends(get_session),
    ) -> ItemRead:
        item = get_item_or_404(session, item_id)
        return update_item(session, item, payload)

    @router.delete(
        "/{item_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="資料を削除する",
        description="誤登録した資料を削除します。",
    )
    def delete_item_endpoint(item_id: int, session: Session = Depends(get_session)) -> Response:
        item = get_item_or_404(session, item_id)
        delete_item(session, item)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    app.include_router(router)
    return app


app = create_app()
