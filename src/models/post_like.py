from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class PostLike(Base):
    __tablename__ = "Post_Likes"

    post_id: Mapped[int] = mapped_column("postId", BigInteger, ForeignKey("post.postId"), primary_key=True)
    client_id: Mapped[str] = mapped_column("clientId", String(36), primary_key=True, comment="UUID")
