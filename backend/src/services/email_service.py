from __future__ import annotations

import html
import json
import logging
from dataclasses import dataclass

from backend.src.config.settings import settings

logger = logging.getLogger("dart.email")


@dataclass(frozen=True)
class EmailSendResult:
    ok: bool
    provider: str
    message_id: str = ""
    error: str = ""


def is_email_enabled() -> bool:
    return settings.email_enabled


def resend_configured() -> bool:
    return bool(settings.resend_api_key and settings.email_from)


def send_email(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    return send_email_result(to_email, subject, html_body, text_body).ok


def send_email_result(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> EmailSendResult:
    if not settings.email_enabled:
        error = "EMAIL_ENABLED=false"
        logger.error("EMAIL_FAILED provider=resend to=%s subject=%s error=%s", to_email, subject, error)
        return EmailSendResult(False, "resend", error=error)
    return _send_resend(to_email, subject, html_body, text_body)


def _send_resend(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> EmailSendResult:
    if not resend_configured():
        error = "Resend no configurado"
        logger.error("EMAIL_FAILED provider=resend to=%s subject=%s error=%s", to_email, subject, error)
        return EmailSendResult(False, "resend", error=error)

    payload = {
        "from": settings.email_from,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "text": text_body or _html_to_text_fallback(html_body),
    }
    logger.info(
        "email_send_attempt provider=resend api_key_prefix=%s payload=%s",
        _api_key_prefix(settings.resend_api_key),
        _safe_json(
            {
                "from": payload["from"],
                "to": payload["to"],
                "subject": payload["subject"],
                "html_length": len(payload["html"]),
                "text_length": len(payload["text"]),
            }
        ),
    )
    try:
        response = _send_with_resend_sdk(payload)
        response_data = _response_to_dict(response)
        message_id = str(response_data.get("id", "") or "")
        if not message_id:
            error = "Resend no retornó id de mensaje"
            logger.error(
                "EMAIL_FAILED provider=resend to=%s subject=%s error=%s response=%s",
                to_email,
                subject,
                error,
                _safe_json(response_data),
            )
            return EmailSendResult(False, "resend", error=error)
        logger.info(
            "EMAIL_SENT_OK provider=resend to=%s subject=%s message_id=%s response=%s",
            to_email,
            subject,
            message_id,
            _safe_json(response_data),
        )
        return EmailSendResult(True, "resend", message_id=message_id)
    except Exception as exc:
        response_data = _exception_response(exc)
        logger.exception(
            "EMAIL_FAILED provider=resend to=%s subject=%s api_key_prefix=%s error=%s response=%s",
            to_email,
            subject,
            _api_key_prefix(settings.resend_api_key),
            exc,
            _safe_json(response_data),
        )
        return EmailSendResult(False, "resend", error=str(exc))


def _send_with_resend_sdk(payload: dict):
    try:
        import resend
    except ImportError as exc:
        raise RuntimeError("SDK oficial de Resend no está instalado. Ejecuta pip install -r requirements.txt.") from exc
    resend.api_key = settings.resend_api_key
    if hasattr(resend, "emails") and hasattr(resend.emails, "send"):
        logger.info("email_sdk_method provider=resend method=resend.emails.send")
        return resend.emails.send(payload)
    if hasattr(resend, "Emails") and hasattr(resend.Emails, "send"):
        logger.info("email_sdk_method provider=resend method=resend.Emails.send")
        return resend.Emails.send(payload)
    raise RuntimeError("SDK oficial de Resend no expone un método de envío compatible.")


def _api_key_prefix(api_key: str) -> str:
    return f"{api_key[:5]}..." if api_key else "<empty>"


def _response_to_dict(response) -> dict:
    if isinstance(response, dict):
        return response
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if hasattr(response, "dict"):
        return response.dict()
    if hasattr(response, "__dict__"):
        return {key: value for key, value in vars(response).items() if not key.startswith("_")}
    return {"raw": str(response)}


def _exception_response(exc: Exception) -> dict:
    data = {
        "type": exc.__class__.__name__,
        "message": str(exc),
    }
    for attr in ("status_code", "status", "code"):
        value = getattr(exc, attr, None)
        if value:
            data[attr] = value
    response = getattr(exc, "response", None)
    if response is not None:
        data["response"] = _response_to_dict(response)
    body = getattr(exc, "body", None)
    if body:
        data["body"] = body
    return data


def _safe_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)[:4000]


def render_email_template(
    title: str,
    intro: str,
    action_text: str,
    action_url: str,
    footer_note: str,
    security_note: str = "Si no esperabas este correo, puedes ignorarlo.",
) -> str:
    safe_title = html.escape(title)
    safe_intro = html.escape(intro)
    safe_action_text = html.escape(action_text)
    safe_action_url = html.escape(action_url, quote=True)
    safe_footer_note = html.escape(footer_note)
    safe_security_note = html.escape(security_note)
    base_url = settings.public_base_url or "https://www.dart-mineria.lat"
    safe_base_url = html.escape(base_url, quote=True)
    logo_url = html.escape(f"{base_url}/static/img/logo-dart.png", quote=True)

    return f"""<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_title}</title>
  </head>
  <body style="margin:0;padding:0;background:#F4F7FA;font-family:Arial,Helvetica,sans-serif;color:#111827;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#F4F7FA;margin:0;padding:28px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#FFFFFF;border:1px solid #E2E8F0;border-radius:14px;overflow:hidden;">
            <tr>
              <td style="padding:28px 32px 18px;text-align:center;background:#0B1726;">
                <img src="{logo_url}" width="128" alt="D.A.R.T" style="display:inline-block;max-width:128px;height:auto;border:0;outline:none;text-decoration:none;">
              </td>
            </tr>
            <tr>
              <td style="padding:32px 32px 10px;">
                <h1 style="margin:0;color:#0B1726;font-size:26px;line-height:1.25;font-weight:800;">{safe_title}</h1>
                <p style="margin:18px 0 0;color:#111827;font-size:16px;line-height:1.65;">{safe_intro}</p>
              </td>
            </tr>
            <tr>
              <td align="center" style="padding:18px 32px 24px;">
                <a href="{safe_action_url}" style="display:inline-block;background:#00A7B5;color:#FFFFFF;text-decoration:none;font-size:16px;font-weight:800;line-height:1;border-radius:10px;padding:16px 28px;">{safe_action_text}</a>
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 24px;">
                <p style="margin:0;color:#64748B;font-size:14px;line-height:1.6;">Si el botón no funciona, copia y pega este enlace en tu navegador:</p>
                <p style="margin:10px 0 0;word-break:break-all;color:#0B1726;font-size:14px;line-height:1.6;"><a href="{safe_action_url}" style="color:#00A7B5;text-decoration:underline;">{safe_action_url}</a></p>
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 30px;">
                <div style="border:1px solid #E2E8F0;border-radius:10px;background:#F8FAFC;padding:14px 16px;color:#64748B;font-size:14px;line-height:1.6;">{safe_security_note}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:22px 32px;text-align:center;border-top:1px solid #E2E8F0;color:#64748B;font-size:13px;line-height:1.6;">
                <strong style="color:#0B1726;">D.A.R.T</strong> · Plataforma interna de seguridad operacional<br>
                <a href="{safe_base_url}" style="color:#00A7B5;text-decoration:none;">{safe_base_url}</a><br>
                {safe_footer_note}
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def render_text_email(title: str, intro: str, action_text: str, action_url: str, footer_note: str) -> str:
    return "\n".join(
        [
            title,
            "",
            intro,
            "",
            f"{action_text}: {action_url}",
            "",
            "Si el botón no funciona, copia y pega el enlace en tu navegador.",
            "Si no esperabas este correo, puedes ignorarlo.",
            "",
            "D.A.R.T - Plataforma interna de seguridad operacional",
            settings.public_base_url or "https://www.dart-mineria.lat",
            footer_note,
        ]
    )


def build_activation_email(action_url: str) -> tuple[str, str, str]:
    subject = "Activa tu cuenta D.A.R.T"
    intro = "Se ha creado una cuenta interna para acceder a la plataforma D.A.R.T. Activa tu acceso y define tu contraseña. Este enlace expira en 48 horas."
    html_body = render_email_template(
        title="Activa tu cuenta D.A.R.T",
        intro=intro,
        action_text="Activar cuenta",
        action_url=action_url,
        footer_note="Enlace válido por 48 horas.",
    )
    text_body = render_text_email("Activa tu cuenta D.A.R.T", intro, "Activar cuenta", action_url, "Enlace válido por 48 horas.")
    return subject, html_body, text_body


def send_activation_email(to_email: str, action_url: str) -> EmailSendResult:
    subject, html_body, text_body = build_activation_email(action_url)
    return send_email_result(to_email, subject, html_body, text_body)


def build_password_reset_email(action_url: str) -> tuple[str, str, str]:
    subject = "Restablece tu contraseña D.A.R.T"
    intro = "Recibimos una solicitud para restablecer la contraseña de tu cuenta D.A.R.T. Este enlace expira en 2 horas."
    html_body = render_email_template(
        title="Restablece tu contraseña D.A.R.T",
        intro=intro,
        action_text="Restablecer contraseña",
        action_url=action_url,
        footer_note="Enlace válido por 2 horas.",
    )
    text_body = render_text_email("Restablece tu contraseña D.A.R.T", intro, "Restablecer contraseña", action_url, "Enlace válido por 2 horas.")
    return subject, html_body, text_body


def send_reset_password_email(to_email: str, action_url: str) -> EmailSendResult:
    subject, html_body, text_body = build_password_reset_email(action_url)
    return send_email_result(to_email, subject, html_body, text_body)


def build_art_assignment_email(action_url: str, art: dict, trabajador_nombre: str) -> tuple[str, str, str]:
    subject = f"ART asignada: {art.get('tipo_tarea', 'Trabajo seguro')}"
    intro = (
        f"Hola {trabajador_nombre or 'trabajador/a'}, tienes una ART asignada para completar tu validación "
        f"de seguridad. Tarea: {art.get('descripcion', '')}. Este enlace es personal y expira en 7 días."
    )
    html_body = render_email_template(
        title="Completa tu ART asignada",
        intro=intro,
        action_text="Responder ART",
        action_url=action_url,
        footer_note="Enlace válido por 7 días.",
        security_note="Este enlace es personal. No lo compartas con otras personas.",
    )
    text_body = render_text_email("Completa tu ART asignada", intro, "Responder ART", action_url, "Enlace válido por 7 días.")
    return subject, html_body, text_body


def send_art_assignment_email(to_email: str, action_url: str, art: dict, trabajador_nombre: str) -> EmailSendResult:
    subject, html_body, text_body = build_art_assignment_email(action_url, art, trabajador_nombre)
    return send_email_result(to_email, subject, html_body, text_body)


def _html_to_text_fallback(html_body: str) -> str:
    return html.unescape(html_body.replace("<br>", "\n").replace("<br>", "\n"))
