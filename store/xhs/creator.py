from sqlalchemy import Column, Integer, String, DateTime, JSON, Index
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select
from typing import Dict

class XhsCreator(Base):
    __tablename__ = "xhs_creator"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, comment="用户ID")
    nickname = Column(String(255), nullable=True, comment="用户昵称")
    avatar = Column(String(255), nullable=True, comment="用户头像")
    desc = Column(String(255), nullable=True, comment="用户简介")
    ip_location = Column(String(255), nullable=True, comment="IP归属地")
    gender = Column(String(255), nullable=True, comment="性别")
    age = Column(String(255), nullable=True, comment="年龄")
    followers = Column(Integer, nullable=True, comment="粉丝数")
    following = Column(Integer, nullable=True, comment="关注数")
    notes = Column(JSON, nullable=True, comment="用户笔记列表，最多保存3篇")
    created_at = Column(DateTime, nullable=False, default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_user_id", user_id),
    )

async def save_creator(user_id: str, creator: Dict):
    """
    保存创作者信息
    Args:
        user_id: 用户ID
        creator: 创作者信息
    """
    async with async_session() as session:
        # 检查是否已存在
        stmt = select(XhsCreator).where(XhsCreator.user_id == user_id)
        result = await session.execute(stmt)
        existing_creator = result.scalar_one_or_none()
        
        creator_data = {
            "user_id": user_id,
            "nickname": creator.get("nickname", ""),
            "avatar": creator.get("avatar", ""),
            "desc": creator.get("desc", ""),
            "ip_location": creator.get("ip_location", ""),
            "gender": creator.get("gender", ""),
            "age": creator.get("age", ""),
            "followers": creator.get("followers", 0),
            "following": creator.get("following", 0),
            "notes": creator.get("notes", [])
        }
        
        if existing_creator:
            # 更新现有记录
            for key, value in creator_data.items():
                setattr(existing_creator, key, value)
        else:
            # 创建新记录
            new_creator = XhsCreator(**creator_data)
            session.add(new_creator)
        
        await session.commit() 