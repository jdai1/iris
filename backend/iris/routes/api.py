from __future__ import annotations

import json
from typing import TypeVar

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from iris.dao import admin
from iris.dao import agent as agent_dao
from iris.dao import bookshelf as bookshelf_dao
from iris.dao import db
from iris.dao import directory as directory_dao
from iris.dao import search as search_dao
from iris.dao import source_profiles as profile_dao
from iris.dao.user_state import get_or_create_firebase_user, get_or_create_local_user
from iris.models import BookshelfCollection, BookshelfStatus, Document, User, UserDocumentMapping
from iris.services.ingestion.crawler import Crawler
from iris.dao.db import init_db
from iris.schemas.enums import AgentMessageRole, CrawlJobStatus, SourceStatus
from iris.dao.sources import get_or_create_source
from iris.schemas.api import (
    AdminCrawlJobSchema,
    AdminIndexRunSchema,
    AdminOverviewSchema,
    AdminSourceSchema,
    AgentChatRequestSchema,
    AgentChatSchema,
    AgentConversationSchema,
    AgentConversationSummarySchema,
    AgentMessageSchema,
    AgentStepSchema,
    BookshelfCollectionCreateSchema,
    BookshelfCollectionItemCreateSchema,
    BookshelfCollectionSchema,
    BookshelfCollectionUpdateSchema,
    BookshelfEntrySchema,
    BookshelfLinkCreateSchema,
    BookshelfUpdateSchema,
    CrawlSchema,
    DocumentDetailSchema,
    DocumentIncomingLinkSchema,
    DocumentOutgoingLinkSchema,
    DocumentSchema,
    DirectorySourceSchema,
    EmbeddingMapSchema,
    GraphEdgeSchema,
    GraphNodeSchema,
    GraphSchema,
    HealthSchema,
    PageSchema,
    SearchResultSchema,
    SearchSchema,
    SourceCreateSchema,
    SourceProfileAnalysisSchema,
    SourceSchema,
    UserSchema,
)
from iris.services.auth import verify_firebase_token
from iris.services.common.config import ADMIN_EMAILS, firebase_auth_enabled, openai_api_key
from iris.services.common.langfuse_tracing import agent_conversation_session_id, agent_trace_metadata, agent_user_id
from iris.services.retrieval.search import search_documents, stream_openai_agentic_chat, synthesize_answer
from iris.services.retrieval.source_profiles import generate_source_profile
from iris.routes.dumps import dump_bookshelf_collection, dump_bookshelf_entry, dump_crawl_job, dump_document, dump_source, dump_source_profile_analysis
from iris.services.ingestion.source_classifier import classify_source_url


app = FastAPI(title="Iris", version="0.1.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):517\d",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

T = TypeVar("T")


async def get_session():
    init_db()
    with db.session_scope():
        yield


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Expected Bearer auth token")
    return token


def get_current_user(
    authorization: str | None = Header(default=None),
    _bound_session=Depends(get_session),
) -> User:
    token = _bearer_token(authorization)
    if token:
        return get_or_create_firebase_user(verify_firebase_token(token))
    if firebase_auth_enabled():
        raise HTTPException(status_code=401, detail="Authentication required")
    return get_or_create_local_user()


def get_optional_user(
    authorization: str | None = Header(default=None),
    _bound_session=Depends(get_session),
) -> User | None:
    token = _bearer_token(authorization)
    if token:
        return get_or_create_firebase_user(verify_firebase_token(token))
    if firebase_auth_enabled():
        return None
    return get_or_create_local_user()


def is_admin_user(user: User) -> bool:
    return bool(user.email and user.email.lower() in ADMIN_EMAILS)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if is_admin_user(user):
        return user
    raise HTTPException(status_code=403, detail="Admin access required")


def dump_user(user: User) -> UserSchema:
    return UserSchema(
        id=user.id,
        firebase_uid=user.firebase_uid,
        email=user.email,
        display_name=user.display_name,
        photo_url=user.photo_url,
        is_admin=is_admin_user(user),
    )


@app.get("/health", response_model=HealthSchema)
def health(_bound_session=Depends(get_session)) -> HealthSchema:
    counts = admin.get_health_counts()
    return HealthSchema(ok=True, sources=counts.sources, documents=counts.documents)


@app.get("/api/me", response_model=UserSchema)
def me(_bound_session=Depends(get_session), user: User = Depends(get_current_user)) -> UserSchema:
    return dump_user(user)


@app.post("/api/sources", response_model=SourceSchema)
def create_source(payload: SourceCreateSchema, _bound_session=Depends(get_session)) -> SourceSchema:
    classification = classify_source_url(payload.url)
    source = get_or_create_source(
        payload.url,
        status=SourceStatus.QUEUED.value,
        force_status=True,
    )
    source.description = classification.reason
    if payload.crawl_now:
        Crawler().crawl_source(
            source,
            max_pages=payload.max_pages,
            max_depth=payload.max_depth,
            active_pages=payload.active_pages,
        )
    return dump_source(source)


@app.get("/api/sources", response_model=list[SourceSchema])
def get_sources(
    status: str | None = SourceStatus.INDEXED.value,
    limit: int = 100,
    _bound_session=Depends(get_session),
) -> list[SourceSchema]:
    return [dump_source(source) for source in admin.get_sources(status=status, limit=limit)]


@app.post("/api/sources/{source_id}/crawl", response_model=CrawlSchema)
def crawl_source_endpoint(
    source_id: int,
    max_pages: int = 80,
    max_depth: int = 3,
    active_pages: int = 4,
    _bound_session=Depends(get_session),
) -> CrawlSchema:
    source = admin.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    job = Crawler().crawl_source(source, max_pages=max_pages, max_depth=max_depth, active_pages=active_pages)
    return dump_crawl_job(job)


@app.get("/api/documents", response_model=PageSchema[DocumentSchema])
def list_documents(
    limit: int = 50,
    offset: int = 0,
    source_id: int | None = None,
    document_type: str | None = None,
    crawl_job_id: int | None = None,
    index_run_id: int | None = None,
    _bound_session=Depends(get_session),
) -> PageSchema[DocumentSchema]:
    documents, total = admin.get_documents_page(
        limit=limit,
        offset=offset,
        source_id=source_id,
        document_type=document_type,
        crawl_job_id=crawl_job_id,
        index_run_id=index_run_id,
    )
    return _page_response([dump_document(document) for document in documents], total, limit, offset)


@app.get("/api/documents/search", response_model=SearchSchema)
def search_documents_picker(
    q: str,
    limit: int = 8,
    _bound_session=Depends(get_session),
    user: User | None = Depends(get_optional_user),
) -> SearchSchema:
    ranked = search_dao.search_documents_for_picker(q, limit=limit)
    return SearchSchema(
        query=q,
        answer="",
        results=_dump_search_results(ranked, user),
    )


@app.get("/api/admin/overview", response_model=AdminOverviewSchema)
def get_admin_overview(_bound_session=Depends(get_session), _admin_user: User = Depends(require_admin)) -> AdminOverviewSchema:
    return admin.get_admin_overview()


@app.get("/api/admin/sources", response_model=PageSchema[AdminSourceSchema])
def admin_sources(
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
    _bound_session=Depends(get_session),
) -> PageSchema[AdminSourceSchema]:
    items, total = admin.get_admin_sources_page(status=status, q=q, limit=limit, offset=offset)
    return _page_response(items, total, limit, offset)


@app.get("/api/directory/sources", response_model=PageSchema[DirectorySourceSchema])
def directory_sources(
    status: str | None = SourceStatus.INDEXED.value,
    q: str | None = None,
    sort: str = "inbound",
    direction: str = "desc",
    limit: int = 50,
    offset: int = 0,
    _bound_session=Depends(get_session),
) -> PageSchema[DirectorySourceSchema]:
    items, total = directory_dao.get_source_directory_page(status=status, q=q, sort=sort, direction=direction, limit=limit, offset=offset)
    return _page_response(items, total, limit, offset)


@app.get("/api/sources/{source_id}/profile-analysis", response_model=SourceProfileAnalysisSchema | None)
def get_source_profile_analysis(source_id: int, _bound_session=Depends(get_session)) -> SourceProfileAnalysisSchema | None:
    source = profile_dao.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    analysis = profile_dao.get_analysis(source_id)
    return dump_source_profile_analysis(analysis) if analysis else None


@app.post("/api/sources/{source_id}/profile-analysis", response_model=SourceProfileAnalysisSchema)
def generate_source_profile_analysis(source_id: int, force: bool = False, _bound_session=Depends(get_session)) -> SourceProfileAnalysisSchema:
    source = profile_dao.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return dump_source_profile_analysis(generate_source_profile(source, force=force))


@app.get("/api/admin/crawl-jobs", response_model=PageSchema[AdminCrawlJobSchema])
def admin_crawl_jobs(
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    source_id: int | None = None,
    index_run_id: int | None = None,
    _bound_session=Depends(get_session),
    _admin_user: User = Depends(require_admin),
) -> PageSchema[AdminCrawlJobSchema]:
    crawl_status = CrawlJobStatus(status) if status and status != "all" else None
    items, total = admin.get_admin_crawl_jobs_page(
        limit=limit,
        offset=offset,
        status=crawl_status,
        source_id=source_id,
        index_run_id=index_run_id,
    )
    return _page_response(items, total, limit, offset)


def _clamped_limit(limit: int) -> int:
    return admin.clamped_limit(limit)


def _page_response(items: list[T], total: int, limit: int, offset: int) -> PageSchema[T]:
    page_limit = _clamped_limit(limit)
    page_offset = max(offset, 0)
    return PageSchema[T](
        items=items,
        total=total,
        limit=page_limit,
        offset=page_offset,
        has_next=page_offset + page_limit < total,
        has_previous=page_offset > 0,
    )


def _dump_bookshelf_entries(user: User, mappings: list[UserDocumentMapping]) -> list[BookshelfEntrySchema]:
    tags = bookshelf_dao.user_tags_for_documents(user, [mapping.document_id for mapping in mappings])
    return [dump_bookshelf_entry(mapping, tags.get(mapping.document_id, [])) for mapping in mappings]


def _dump_bookshelf_collection(collection: BookshelfCollection) -> BookshelfCollectionSchema:
    document_ids = [item.document_id for item in collection.items]
    mappings = (
        db.current_session()
        .execute(
            select(UserDocumentMapping)
            .options(joinedload(UserDocumentMapping.document).joinedload(Document.source))
            .where(UserDocumentMapping.user_id == collection.user_id)
            .where(UserDocumentMapping.document_id.in_(document_ids))
        )
        .scalars()
        .all()
        if document_ids
        else []
    )
    by_document_id = {mapping.document_id: mapping for mapping in mappings}
    tags = bookshelf_dao.user_tags_for_documents(collection.user, document_ids)
    entries = [
        dump_bookshelf_entry(by_document_id[item.document_id], tags.get(item.document_id, []))
        for item in collection.items
        if item.document_id in by_document_id
    ]
    return dump_bookshelf_collection(collection, entries)


def _dump_document_for_user(document: Document, user: User) -> DocumentSchema:
    payload = dump_document(document)
    mapping = (
        db.current_session()
        .execute(
            select(UserDocumentMapping)
            .where(UserDocumentMapping.user_id == user.id)
            .where(UserDocumentMapping.document_id == document.id)
        )
        .scalar_one_or_none()
    )
    if mapping:
        payload.bookshelf_status = bookshelf_dao.effective_status(mapping)
        payload.bookshelf_favorited = mapping.favorited_at is not None
    return payload


def _dump_search_results_for_user(results, user: User) -> list[SearchResultSchema]:
    return [
        SearchResultSchema(document=_dump_document_for_user(item.document, user), reason=item.reason)
        for item in results
    ]


def _dump_search_results(results, user: User | None = None) -> list[SearchResultSchema]:
    if user:
        return _dump_search_results_for_user(results, user)
    return [
        SearchResultSchema(document=dump_document(item.document), reason=item.reason)
        for item in results
    ]


def _resolve_document_uuid(document_uuid: str) -> Document | None:
    """Resolve a public UUID, while accepting a positive integer legacy ID."""
    session = db.current_session()
    document = session.scalar(select(Document).where(Document.uuid == document_uuid))
    if document is not None:
        return document
    if len(document_uuid) <= 10 and document_uuid.isascii() and document_uuid.isdigit():
        legacy_id = int(document_uuid)
        if 0 < legacy_id <= 2_147_483_647:
            return session.get(Document, legacy_id)
    return None


@app.get("/api/admin/index-runs", response_model=PageSchema[AdminIndexRunSchema])
def admin_index_runs(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    _bound_session=Depends(get_session),
    _admin_user: User = Depends(require_admin),
) -> PageSchema[AdminIndexRunSchema]:
    items, total = admin.get_admin_index_runs_page(limit=limit, offset=offset, status=status)
    return _page_response(items, total, limit, offset)


@app.get("/api/documents/{document_uuid}", response_model=DocumentDetailSchema)
def get_document(document_uuid: str, _bound_session=Depends(get_session)) -> DocumentDetailSchema:
    resolved = _resolve_document_uuid(document_uuid)
    document, outgoing, incoming = admin.get_document_detail(resolved.id) if resolved else (None, [], [])
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    payload = dump_document(document).model_dump()
    linked_ids = {link.target_document_id for link in outgoing if link.target_document_id}
    linked_ids.update(link.source_document_id for link in incoming)
    linked_uuids = dict(db.current_session().execute(select(Document.id, Document.uuid).where(Document.id.in_(linked_ids))).all())
    return DocumentDetailSchema(
        **payload,
        extracted_text=document.extracted_text,
        outgoing_links=[
            DocumentOutgoingLinkSchema(
                target_url=link.target_url,
                target_domain=link.target_domain,
                target_document_id=link.target_document_id,
                target_document_uuid=linked_uuids.get(link.target_document_id),
                anchor_text=link.anchor_text,
                context=link.context,
            )
            for link in outgoing
        ],
        incoming_links=[
            DocumentIncomingLinkSchema(
                source_document_id=link.source_document_id,
                source_document_uuid=linked_uuids[link.source_document_id],
                target_url=link.target_url,
                anchor_text=link.anchor_text,
            )
            for link in incoming
        ],
    )


@app.get("/api/search", response_model=SearchSchema)
def search(
    q: str,
    limit: int = 12,
    _bound_session=Depends(get_session),
    user: User | None = Depends(get_optional_user),
) -> SearchSchema:
    _search_row, ranked = search_documents(q, limit=limit, persist=False)
    answer = synthesize_answer(q, ranked)
    return SearchSchema(
        query=q,
        answer=answer or "",
        results=_dump_search_results(ranked, user),
    )


@app.post("/api/agent-chat", response_model=AgentChatSchema)
def agent_chat(
    payload: AgentChatRequestSchema,
    _bound_session=Depends(get_session),
    user: User = Depends(get_current_user),
) -> AgentChatSchema:
    conversation, user_message, assistant_message, result = agent_dao.create_agent_chat(
        payload.message,
        user=user,
        limit=payload.limit,
        conversation_id=payload.conversation_id,
        conversation_uuid=payload.conversation_uuid,
    )
    return AgentChatSchema(
        conversation_id=conversation.id,
        conversation_uuid=conversation.uuid,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        message=payload.message,
        answer=result.answer,
        results=_dump_search_results_for_user(result.results, user),
        steps=[
            AgentStepSchema(
                **_agent_step_payload(step),
            )
            for step in result.steps
        ],
    )


@app.post("/api/agent-chat/stream")
def agent_chat_stream(
    payload: AgentChatRequestSchema,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    return StreamingResponse(
        _agent_chat_stream_events(payload, authorization),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _agent_chat_stream_events(payload: AgentChatRequestSchema, authorization: str | None):
    try:
        init_db()
        with db.session_scope():
            user = _current_user_from_header(authorization)
            conversation, user_message = agent_dao.start_agent_chat(
                payload.message,
                user=user,
                conversation_id=payload.conversation_id,
                conversation_uuid=payload.conversation_uuid,
            )
            conversation_id = conversation.id
            conversation_uuid = conversation.uuid
            user_message_id = user_message.id
        yield _sse(
            "conversation",
            {
                "conversation_id": conversation_id,
                "conversation_uuid": conversation_uuid,
                "user_message_id": user_message_id,
                "message": payload.message,
            },
        )

        if not openai_api_key():
            yield _sse("error", {"message": "OpenAI API key is required for agent chat", "type": "MissingOpenAIKeyError"})
            return

        with db.session_scope():
            user = _current_user_from_header(authorization)
            conversation = agent_dao.get_agent_conversation(conversation_id, user=user)
            if conversation is None:
                yield _sse("error", {"message": "Conversation not found", "type": "ConversationNotFoundError"})
                return
            user_message = next((message for message in conversation.messages if message.id == user_message_id), None)
            if user_message is None:
                yield _sse("error", {"message": "User message not found", "type": "UserMessageNotFoundError"})
                return
            conversation_context = _agent_conversation_context(conversation, current_user_message_id=user_message_id)
            async for event in stream_openai_agentic_chat(
                payload.message,
                limit=payload.limit,
                conversation_context=conversation_context,
                session_id=agent_conversation_session_id(conversation.uuid),
                user_id=agent_user_id(user.id),
                trace_metadata=agent_trace_metadata(
                    conversation_id=conversation_id,
                    conversation_uuid=conversation.uuid,
                    user_id=user.id,
                    firebase_uid=user.firebase_uid,
                ),
            ):
                async for chunk in _agent_chat_event_chunks(event, conversation, user_message, payload):
                    yield chunk
    except Exception as exc:
        yield _sse("error", {"message": str(exc), "type": type(exc).__name__})


def _current_user_from_header(authorization: str | None) -> User:
    token = _bearer_token(authorization)
    if token:
        return get_or_create_firebase_user(verify_firebase_token(token))
    if firebase_auth_enabled():
        raise HTTPException(status_code=401, detail="Authentication required")
    return get_or_create_local_user()


async def _agent_chat_event_chunks(event, conversation, user_message, payload: AgentChatRequestSchema):
    if event.event == "tool_result" and event.step:
        yield _sse(
            "tool_result",
            {
                "step": _agent_step_payload(event.step),
                "hits": [
                    {
                        "title": row.document.title or row.document.url,
                        "source_domain": row.document.source.canonical_domain,
                        "reason": row.reason,
                    }
                    for row in event.rows[:5]
                ],
            },
        )
        return

    if event.event == "step" and event.step:
        yield _sse("step", {"step": _agent_step_payload(event.step)})
        return

    if event.event == "final" and event.result:
        assistant_message = agent_dao.finish_agent_chat(conversation, event.result)
        yield _sse(
            "final",
            {
                "conversation_id": conversation.id,
                "conversation_uuid": conversation.uuid,
                "user_message_id": user_message.id,
                "assistant_message_id": assistant_message.id,
                "message": payload.message,
                "answer": event.result.answer,
                "steps": [_agent_step_payload(step) for step in event.result.steps],
                "results": [
                    {
                        "document": _dump_document_for_user(item.document, conversation.user).model_dump(),
                        "reason": item.reason,
                    }
                    for item in event.result.results
                ],
            },
        )
        yield _sse("done", {"conversation_id": conversation.id, "conversation_uuid": conversation.uuid})
        return


def _agent_step_payload(step) -> dict[str, object]:
    kind = step.kind.value if hasattr(step.kind, "value") else str(step.kind)
    tool = step.tool.value if hasattr(step.tool, "value") else step.tool
    return {
        "kind": kind,
        "title": step.title,
        "detail": step.detail,
        "tool": tool,
        "query": step.query,
        "hits": step.hits,
    }


def _agent_conversation_context(conversation, *, current_user_message_id: int) -> str:
    lines: list[str] = []
    prior_messages = [message for message in conversation.messages if message.id != current_user_message_id]
    for message in prior_messages:
        role = "User" if message.role == AgentMessageRole.USER else "Iris"
        content = " ".join(message.content.split())
        if len(content) > 700:
            content = f"{content[:697]}..."
        lines.append(f"{role}: {content}")
        if message.role == AgentMessageRole.ASSISTANT and message.results:
            lines.append("Iris recommended links:")
            for result in message.results[:8]:
                document = result.document
                title = document.title or document.url
                summary = " ".join((document.summary or "").split())
                if len(summary) > 260:
                    summary = f"{summary[:257]}..."
                lines.append(
                    f"- internal_ref={document.id}; title={title}; source={document.source.canonical_domain}; "
                    f"url={document.url}; summary={summary}"
                )
    return "\n".join(lines)


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@app.get("/api/agent-conversations", response_model=list[AgentConversationSummarySchema])
def agent_conversations(
    limit: int = 30,
    offset: int = 0,
    q: str | None = None,
    _bound_session=Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[AgentConversationSummarySchema]:
    conversations = agent_dao.list_agent_conversations(limit=limit, offset=offset, q=q, user=user)
    return [
        AgentConversationSummarySchema(
            id=conversation.id,
            uuid=conversation.uuid,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=len(conversation.messages),
        )
        for conversation in conversations
    ]


@app.get("/api/agent-conversations/{conversation_identifier}", response_model=AgentConversationSchema)
def agent_conversation(
    conversation_identifier: str,
    _bound_session=Depends(get_session),
    user: User = Depends(get_current_user),
) -> AgentConversationSchema:
    conversation = (
        agent_dao.get_agent_conversation(int(conversation_identifier), user=user)
        if conversation_identifier.isdigit()
        else agent_dao.get_agent_conversation_by_uuid(conversation_identifier, user=user)
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return AgentConversationSchema(
        id=conversation.id,
        uuid=conversation.uuid,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[_dump_agent_message(message, user) for message in conversation.messages],
    )


def _dump_agent_message(message, user: User) -> AgentMessageSchema:
    steps = [
        AgentStepSchema(
            kind=step.get("kind", ""),
            title=step.get("title", ""),
            detail=step.get("detail", ""),
            tool=step.get("tool"),
            query=step.get("query"),
            hits=step.get("hits"),
        )
        for step in (message.steps or [])
    ]
    return AgentMessageSchema(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        steps=steps,
        results=[
            SearchResultSchema(document=_dump_document_for_user(result.document, user), reason=result.reason)
            for result in message.results
        ],
    )


@app.get("/api/bookshelf", response_model=PageSchema[BookshelfEntrySchema])
def list_bookshelf(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _bound_session=Depends(get_session),
    user: User = Depends(get_current_user),
) -> PageSchema[BookshelfEntrySchema]:
    if status == "favorite":
        mappings, total = bookshelf_dao.favorite_entries(user, limit=limit, offset=offset)
    else:
        parsed_status = None
        if status:
            try:
                parsed_status = BookshelfStatus(status)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid bookshelf status") from exc
        mappings, total = bookshelf_dao.list_entries(user, status=parsed_status, limit=limit, offset=offset)
    return _page_response(_dump_bookshelf_entries(user, mappings), total, limit, offset)


@app.patch("/api/documents/{document_uuid}/bookshelf", response_model=BookshelfEntrySchema)
def update_document_bookshelf(
    document_uuid: str,
    payload: BookshelfUpdateSchema,
    _bound_session=Depends(get_session),
    user: User = Depends(get_current_user),
) -> BookshelfEntrySchema:
    document = _resolve_document_uuid(document_uuid)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    fields = payload.model_fields_set
    mapping = bookshelf_dao.update_entry(
        user,
        document,
        status=payload.status,
        favorited=payload.favorited,
        note=payload.note,
        intent_note=payload.intent_note,
        tags=payload.tags,
        update_note="note" in fields,
        update_intent_note="intent_note" in fields,
    )
    tags = bookshelf_dao.user_tags_for_documents(user, [document.id]).get(document.id, [])
    return dump_bookshelf_entry(mapping, tags)


@app.post("/api/bookshelf/links", response_model=BookshelfEntrySchema)
def create_bookshelf_link(
    payload: BookshelfLinkCreateSchema,
    _bound_session=Depends(get_session),
    user: User = Depends(get_current_user),
) -> BookshelfEntrySchema:
    try:
        mapping = bookshelf_dao.create_entry_for_url(
            user,
            url=payload.url,
            title=payload.title,
            note=payload.note,
            intent_note=payload.intent_note,
            tags=payload.tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.collection_id is not None:
        item = bookshelf_dao.add_collection_item(user, payload.collection_id, mapping.document)
        if item is None:
            raise HTTPException(status_code=404, detail="Collection not found")
    if payload.crawl_now:
        try:
            Crawler().crawl_source(mapping.document.source, max_pages=5, max_depth=1, active_pages=1)
        except Exception:
            pass
    tags = bookshelf_dao.user_tags_for_documents(user, [mapping.document_id]).get(mapping.document_id, [])
    return dump_bookshelf_entry(mapping, tags)


@app.get("/api/bookshelf/collections", response_model=list[BookshelfCollectionSchema])
def list_bookshelf_collections(
    _bound_session=Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[BookshelfCollectionSchema]:
    return [_dump_bookshelf_collection(collection) for collection in bookshelf_dao.list_collections(user)]


@app.post("/api/bookshelf/collections", response_model=BookshelfCollectionSchema)
def create_bookshelf_collection(
    payload: BookshelfCollectionCreateSchema,
    _bound_session=Depends(get_session),
    user: User = Depends(get_current_user),
) -> BookshelfCollectionSchema:
    try:
        collection = bookshelf_dao.create_collection(
            user,
            name=payload.name,
            description=payload.description,
            visibility=payload.visibility,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _dump_bookshelf_collection(collection)


@app.patch("/api/bookshelf/collections/{collection_id}", response_model=BookshelfCollectionSchema)
def update_bookshelf_collection(
    collection_id: int,
    payload: BookshelfCollectionUpdateSchema,
    _bound_session=Depends(get_session),
    user: User = Depends(get_current_user),
) -> BookshelfCollectionSchema:
    fields = payload.model_fields_set
    try:
        collection = bookshelf_dao.update_collection(
            user,
            collection_id,
            name=payload.name,
            description=payload.description,
            visibility=payload.visibility,
            update_name="name" in fields,
            update_description="description" in fields,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return _dump_bookshelf_collection(collection)


@app.delete("/api/bookshelf/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bookshelf_collection(
    collection_id: int,
    _bound_session=Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    deleted = bookshelf_dao.delete_collection(user, collection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Collection not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/bookshelf/collections/{collection_id}/items", response_model=BookshelfCollectionSchema)
def add_bookshelf_collection_item(
    collection_id: int,
    payload: BookshelfCollectionItemCreateSchema,
    _bound_session=Depends(get_session),
    user: User = Depends(get_current_user),
) -> BookshelfCollectionSchema:
    document = _resolve_document_uuid(payload.document_uuid) if payload.document_uuid else (
        db.current_session().get(Document, payload.document_id) if payload.document_id else None
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    item = bookshelf_dao.add_collection_item(user, collection_id, document, position=payload.position)
    if item is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    collection = bookshelf_dao.get_collection(user, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return _dump_bookshelf_collection(collection)


@app.delete("/api/bookshelf/collections/{collection_id}/items/{document_uuid}", response_model=BookshelfCollectionSchema)
def remove_bookshelf_collection_item(
    collection_id: int,
    document_uuid: str,
    _bound_session=Depends(get_session),
    user: User = Depends(get_current_user),
) -> BookshelfCollectionSchema:
    document = _resolve_document_uuid(document_uuid)
    removed = document is not None and bookshelf_dao.remove_collection_item(user, collection_id, document.id)
    if not removed:
        raise HTTPException(status_code=404, detail="Collection item not found")
    collection = bookshelf_dao.get_collection(user, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return _dump_bookshelf_collection(collection)


@app.get("/api/shared/bookshelf/collections/{share_token}", response_model=BookshelfCollectionSchema)
def get_shared_bookshelf_collection(
    share_token: str,
    _bound_session=Depends(get_session),
) -> BookshelfCollectionSchema:
    collection = bookshelf_dao.get_shared_collection(share_token)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return _dump_bookshelf_collection(collection)


@app.get("/api/embedding-map", response_model=EmbeddingMapSchema)
def embedding_map(
    limit: int = 3000,
    _bound_session=Depends(get_session),
) -> EmbeddingMapSchema:
    return admin.get_embedding_map(limit=limit)


@app.get("/api/graph", response_model=GraphSchema)
def graph(
    mode: str = "documents",
    document_id: int | None = None,
    document_uuid: str | None = None,
    source_id: int | None = None,
    domain: str | None = None,
    limit: int = 120,
    depth: int = 1,
    _bound_session=Depends(get_session),
) -> GraphSchema:
    if mode == "sources":
        sources, edges = admin.get_source_graph_rows(source_id=source_id, domain=domain, limit=limit, depth=depth)
        source_by_id = {source.id: source for source in sources}
        nodes = [
            GraphNodeSchema(
                id=f"source:{source.id}",
                label=source.name or source.canonical_domain,
                type=source.status,
                domain=source.canonical_domain,
                url=source.url,
                subtitle=source.description,
                size=1.0 + min(9.0, sum(weight for src, dst, weight in edges if src == source.id or dst == source.id) ** 0.5),
            )
            for source in sources
        ]
        graph_edges = [
            GraphEdgeSchema(
                source=f"source:{source}",
                target=f"source:{target}",
                label=f"{weight} links",
                weight=float(weight),
            )
            for source, target, weight in edges
            if source in source_by_id and target in source_by_id
        ]
        return GraphSchema(nodes=nodes, edges=graph_edges)

    focused_document = _resolve_document_uuid(document_uuid) if document_uuid else None
    if document_uuid and focused_document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    documents, links = admin.get_graph_rows(focused_document.id if focused_document else document_id, limit=limit)
    document_uuids = {document.id: document.uuid for document in documents}
    nodes = [
        GraphNodeSchema(
            id=f"doc:{document.uuid}",
            label=document.title or document.source.canonical_domain,
            type=document.document_type,
            domain=document.source.canonical_domain,
            url=document.url,
            subtitle=document.author or document.source.canonical_domain,
            summary=document.summary,
            size=1.0 + min(9.0, len((document.summary or document.extracted_text or "").split()) ** 0.25),
        )
        for document in documents
    ]
    edges = [
        GraphEdgeSchema(source=f"doc:{document_uuids[link.source_document_id]}", target=f"doc:{document_uuids[link.target_document_id]}", label=link.anchor_text, weight=1.0)
        for link in links
        if link.target_document_id in document_uuids and link.source_document_id in document_uuids
    ]
    return GraphSchema(nodes=nodes, edges=edges)


@app.get("/api/graph/sources/search", response_model=list[AdminSourceSchema])
def graph_source_search(
    q: str,
    limit: int = 20,
    _bound_session=Depends(get_session),
) -> list[AdminSourceSchema]:
    return admin.search_graph_sources(q, limit=limit)
