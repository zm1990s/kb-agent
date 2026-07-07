-- M0：仅启用需要的扩展；业务表交给 M1/M2 的迁移。
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
