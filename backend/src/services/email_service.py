from __future__ import annotations

import html
import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from backend.src.config.settings import settings

logger = logging.getLogger("dart.email")


def is_email_enabled() -> bool:
    return settings.email_enabled


def smtp_configured() -> bool:
    return all(
        [
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_password,
            settings.smtp_from,
        ]
    )


def resend_configured() -> bool:
    return bool(settings.resend_api_key and (settings.email_from or settings.smtp_from))


def send_email(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    if not settings.email_enabled:
        logger.info("EMAIL_ENABLED=false; no se envía correo a %s.", to_email)
        return False
    if settings.email_provider == "resend":
        return _send_resend(to_email, subject, html_body, text_body)
    if not smtp_configured():
        logger.error("SMTP no está configurado correctamente.")
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = to_email
    message.set_content(text_body or _html_to_text_fallback(html_body))
    message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
        logger.info("Correo enviado a %s con asunto %s.", to_email, subject)
        return True
    except Exception:
        logger.exception("No se pudo enviar correo a %s con asunto %s.", to_email, subject)
        return False


def _send_resend(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    if not resend_configured():
        logger.error("Resend no está configurado correctamente.")
        return False

    payload = {
        "from": settings.email_from or settings.smtp_from,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
        "text": text_body or _html_to_text_fallback(html_body),
    }
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if 200 <= response.status < 300:
                logger.info("Correo Resend enviado a %s con asunto %s.", to_email, subject)
                return True
            logger.error("Resend respondió estado %s al enviar a %s.", response.status, to_email)
            return False
    except urllib.error.HTTPError as exc:
        logger.error("Resend respondió estado %s al enviar a %s.", exc.code, to_email)
        return False
    except Exception:
        logger.exception("No se pudo enviar correo Resend a %s con asunto %s.", to_email, subject)
        return False


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


def _html_to_text_fallback(html_body: str) -> str:
    return html.unescape(html_body.replace("<br>", "\n").replace("<br>", "\n"))
