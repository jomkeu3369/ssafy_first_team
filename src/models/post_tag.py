from sqlalchemy import BigInteger, Column, ForeignKey, Table

from src.models.base import Base


post_tags = Table(
    "Post_Tags",
    Base.metadata,
    Column("postId", BigInteger, ForeignKey("post.postId"), primary_key=True),
    Column("tagId", BigInteger, ForeignKey("Tag.tagId"), primary_key=True),
)
