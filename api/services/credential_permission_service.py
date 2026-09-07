from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from core.db import session_factory
from models.account import Account
from models.credential_permission import CredentialPermission
from models.enums import PermissionEnum


class CredentialAccessDeniedError(Exception):
    """
    Raised at runtime when a caller tries to use a credential their visibility
    setting excludes them from. Mirrors the invariants of
    ``apply_visibility_filter`` for lookup paths that don't apply that filter
    (workflow runtime, RAG pipeline runtime, etc.).
    """

    def __init__(self, credential_id: str, message: str | None = None) -> None:
        super().__init__(message or f"credential {credential_id} is not accessible to the current caller")
        self.credential_id = credential_id


class CredentialPermissionService:
    """
    Shared service for per-credential access control.
    Mirrors DatasetPermissionService but supports all credential types
    via a credential_type discriminator.
    """

    @classmethod
    def get_partial_member_list(cls, credential_id: str, credential_type: str, *, session: Session) -> Sequence[str]:
        """Return account_ids that have partial-member access to a credential."""
        return session.scalars(
            select(CredentialPermission.account_id).where(
                CredentialPermission.credential_id == credential_id,
                CredentialPermission.credential_type == credential_type,
            )
        ).all()

    @classmethod
    def apply_visibility_filter(
        cls,
        query,
        *,
        model_id_column: InstrumentedAttribute,
        model_user_id_column: InstrumentedAttribute,
        model_visibility_column: InstrumentedAttribute,
        credential_type: str,
        user: Account,
    ):
        """
        Add WHERE clauses to a SQLAlchemy query so it only returns credentials
        visible to the given user.

        - all_team_members: always visible
        - only_me: visible only to the creator (user.id matches)
        - partial_members: visible to the creator OR users in credential_permissions
        - Legacy rows with NULL user_id are treated as all_team_members
        - No admin bypass: personal credentials are private regardless of role
        """
        # Subquery: credential_ids where user has partial-member permission
        partial_subquery = (
            select(CredentialPermission.credential_id)
            .where(
                CredentialPermission.credential_type == credential_type,
                CredentialPermission.account_id == user.id,
            )
            .correlate_except(CredentialPermission)
        )

        return query.where(
            or_(
                # all_team is always visible
                model_visibility_column == PermissionEnum.ALL_TEAM,
                # legacy rows with NULL user_id treated as all_team
                model_user_id_column.is_(None),
                # only_me: creator sees their own
                (model_user_id_column == user.id),
                # partial_members: user is in the permission table
                model_id_column.in_(partial_subquery),
            )
        )

    @classmethod
    def enforce_runtime_access(
        cls,
        *,
        credential_id: str,
        credential_type: str,
        visibility: PermissionEnum,
        owner_user_id: str | None,
        current_user_id: str | None,
    ) -> None:
        """
        Fail-closed runtime check that mirrors ``apply_visibility_filter``.

        Runtime credential lookups (workflow execution, RAG pipeline ingestion,
        etc.) resolve a credential by tenant_id + provider or by credential_id
        without applying the visibility filter. This check enforces the same
        invariants at that point so a workflow node that references another
        member's only_me credential (or a workflow published to end-users)
        cannot silently execute with credentials the current caller could
        never have picked in the UI.

        - ALL_TEAM  → always allowed
        - Legacy rows (owner_user_id is None) → treated as ALL_TEAM, allowed
        - ONLY_ME   → allowed only when current_user_id matches the owner;
          anonymous / cross-workspace callers (current_user_id is None or
          differs) are rejected
        - PARTIAL_TEAM → allowed for the owner, plus any account listed in
          credential_permissions
        - Any unrecognised visibility value falls back to reject (safe default)

        Callers pass ``current_user_id=None`` from headless / system contexts
        (background jobs, migrations). Rejecting on ONLY_ME there is the
        intended behavior — personal credentials aren't meant to run behind
        an anonymous invoker; workflows that need to run headlessly should
        use ALL_TEAM credentials instead.
        """
        if visibility == PermissionEnum.ALL_TEAM:
            return
        if owner_user_id is None:
            # Legacy pre-visibility rows: treat as workspace-shared to preserve
            # existing behavior. New writes always populate owner_user_id.
            return
        if visibility == PermissionEnum.ONLY_ME:
            if current_user_id is not None and current_user_id == owner_user_id:
                return
            raise CredentialAccessDeniedError(
                credential_id,
                (
                    f"credential {credential_id} is scoped to only its creator; "
                    "the current caller is not the owner"
                ),
            )
        if visibility == PermissionEnum.PARTIAL_TEAM:
            if current_user_id is not None and current_user_id == owner_user_id:
                return
            if current_user_id is None:
                raise CredentialAccessDeniedError(credential_id)
            with session_factory.create_session() as session:
                allowed_ids = set(
                    cls.get_partial_member_list(
                        credential_id=credential_id,
                        credential_type=credential_type,
                        session=session,
                    )
                )
            if current_user_id in allowed_ids:
                return
            raise CredentialAccessDeniedError(credential_id)
        # Unknown visibility value — fail closed rather than silently allow.
        raise CredentialAccessDeniedError(
            credential_id,
            f"credential {credential_id} has an unrecognised visibility ({visibility!r})",
        )
