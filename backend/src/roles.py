ADMIN = "admin"
SUPERVISOR = "supervisor"
USER = "trabajador"

ROLES = {ADMIN, SUPERVISOR, USER}
ROLE_LABELS = {
    ADMIN: "Admin",
    SUPERVISOR: "Supervisor",
    USER: "Trabajador",
}


def can_review_art(role: str) -> bool:
    return role in {ADMIN, SUPERVISOR}


def can_create_art(role: str) -> bool:
    return role in {ADMIN, SUPERVISOR}


def can_manage_users(role: str) -> bool:
    return role == ADMIN
