"""One-level document folders."""

from typing import Sequence, Union

from alembic import op

revision: str = "0002_folders"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        create table folders (
          id bigint generated always as identity primary key,
          name text not null,
          created_at timestamptz not null default now(),
          updated_at timestamptz not null default now(),
          constraint folders_name_chk check (char_length(btrim(name)) > 0)
        )
        """
    )
    op.execute("create index folders_created_at_idx on folders (created_at desc)")
    op.execute(
        """
        alter table documents
          add column folder_id bigint references folders (id) on delete set null
        """
    )
    op.execute("create index documents_folder_id_idx on documents (folder_id)")


def downgrade() -> None:
    op.execute("alter table documents drop column if exists folder_id")
    op.execute("drop table if exists folders")
