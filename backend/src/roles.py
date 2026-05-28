ADMIN = "admin"
SUPERVISOR = "supervisor"
USER = "user"

ROLES = {ADMIN, SUPERVISOR, USER}
ROLE_LABELS = {
    ADMIN: "Admin",
    SUPERVISOR: "Supervisor",
    USER: "Usuario",
}


def can_review_art(role: str) -> bool:
    return role in {ADMIN, SUPERVISOR}


def can_manage_users(role: str) -> bool:
    return role == ADMIN
