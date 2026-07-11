from fastapi import APIRouter

router = APIRouter()


@router.get("/api/guestbook")
def list_guestbook_entries():
    # TODO: cursor 기반 페이지네이션, 10개씩, created_at DESC
    return {"entries": [], "next_cursor": None}


@router.post("/api/guestbook")
def create_guestbook_entry():
    # TODO: content(최대 500자) + rating(1~5, optional) + shop_tags[] insert
    return {"id": "dummy-entry-id", "content": "", "rating": None, "shop_tags": []}
