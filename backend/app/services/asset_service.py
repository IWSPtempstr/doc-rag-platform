"""Asset service — image asset management (v2.0)"""

from sqlalchemy.orm import Session
from app.models import ImageAssetModel


def get_assets_for_document(db: Session, document_id: int) -> list[ImageAssetModel]:
    return (
        db.query(ImageAssetModel)
        .filter(ImageAssetModel.document_id == document_id)
        .order_by(ImageAssetModel.source_page, ImageAssetModel.id)
        .all()
    )


def get_asset(db: Session, asset_id: int) -> ImageAssetModel | None:
    return db.query(ImageAssetModel).filter(ImageAssetModel.id == asset_id).first()


def bind_image_to_chunks(db: Session, asset_id: int, chunk_ids: list[str]):
    asset = db.query(ImageAssetModel).filter(ImageAssetModel.id == asset_id).first()
    if asset:
        existing = set(asset.associated_chunks or [])
        existing.update(chunk_ids)
        asset.associated_chunks = list(existing)
        db.commit()
