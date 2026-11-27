from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import DuplicateResourceError
from app.schemas.user import UserInDB, UserResponse, UserRole


class UserRepository:
    COLLECTION_NAME = "users"

    def __init__(self, db: AsyncDatabase) -> None:
        self.collection = db[self.COLLECTION_NAME]

    async def ensure_indexes(self) -> None:
        await self.collection.create_index("email", unique=True, name="uq_users_email")
        await self.collection.create_index(
            [("role", 1), ("is_active", 1)],
            name="ix_users_role_active",
        )

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _to_user_response(doc: dict[str, Any]) -> UserResponse:
        return UserResponse(
            id=str(doc["_id"]),
            email=doc["email"],
            full_name=doc["full_name"],
            role=UserRole(doc["role"]),
            is_active=bool(doc["is_active"]),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    @staticmethod
    def _to_user_in_db(doc: dict[str, Any]) -> UserInDB:
        return UserInDB(
            id=str(doc["_id"]),
            email=doc["email"],
            full_name=doc["full_name"],
            role=UserRole(doc["role"]),
            is_active=bool(doc["is_active"]),
            password_hash=doc["password_hash"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    async def get_by_email(self, email: str) -> UserInDB | None:
        doc = await self.collection.find_one({"email": self._normalize_email(email)})
        if not doc:
            return None
        return self._to_user_in_db(doc)

    async def get_by_id(self, user_id: str) -> UserInDB | None:
        if not ObjectId.is_valid(user_id):
            return None
        doc = await self.collection.find_one({"_id": ObjectId(user_id)})
        if not doc:
            return None
        return self._to_user_in_db(doc)

    async def create(
        self,
        *,
        email: str,
        full_name: str,
        password_hash: str,
        role: UserRole,
        is_active: bool = True,
    ) -> UserResponse:
        now = datetime.now(timezone.utc)
        document: dict[str, Any] = {
            "email": self._normalize_email(email),
            "full_name": full_name.strip(),
            "password_hash": password_hash,
            "role": role.value,
            "is_active": is_active,
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = await self.collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise DuplicateResourceError("El correo electrónico ya está registrado") from exc

        document["_id"] = result.inserted_id
        return self._to_user_response(document)

    async def list_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[UserResponse], int]:
        query: dict[str, Any] = {}
        if role is not None:
            query["role"] = role.value
        if is_active is not None:
            query["is_active"] = is_active

        skip = (page - 1) * page_size
        total = await self.collection.count_documents(query)
        cursor = (
            self.collection.find(query, projection={"password_hash": 0})
            .sort("created_at", -1)
            .skip(skip)
            .limit(page_size)
        )
        docs = [self._to_user_response(doc) async for doc in cursor]
        return docs, total

    async def update(self, user_id: str, update_fields: dict[str, Any]) -> UserResponse | None:
        if not ObjectId.is_valid(user_id):
            return None

        fields = {**update_fields, "updated_at": datetime.now(timezone.utc)}
        doc = await self.collection.find_one_and_update(
            {"_id": ObjectId(user_id)},
            {"$set": fields},
            projection={"password_hash": 0},
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            return None
        return self._to_user_response(doc)

    async def find_emails_by_ids(self, ids: list[ObjectId]) -> dict[ObjectId, str]:
        if not ids:
            return {}
        cursor = self.collection.find({"_id": {"$in": ids}}, {"email": 1})
        return {doc["_id"]: doc["email"] async for doc in cursor}
