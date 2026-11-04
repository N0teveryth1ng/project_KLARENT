import uuid as uuid_pkg
from sqlalchemy import TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == 'postgresql':
            if isinstance(value, uuid_pkg.UUID):
                return value
            return uuid_pkg.UUID(str(value))
        else:
            if isinstance(value, uuid_pkg.UUID):
                return str(value)
            return str(uuid_pkg.UUID(str(value)))

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid_pkg.UUID):
            return value
        return uuid_pkg.UUID(str(value))
