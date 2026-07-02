"""
server/services/email_service.py
Servicio de envío de correo transaccional via Brevo (API REST).

Justificación:
    Usamos la API REST de Brevo directamente con 'requests' para no
    añadir dependencias pesadas (el SDK oficial requiere varias librerías).
    Solo necesitamos un endpoint simple: POST /v3/smtp/email.
"""
from __future__ import annotations

import requests

from server.config import BREVO_API_KEY, BREVO_SENDER_EMAIL, BREVO_SENDER_NAME, SERVER_BASE_URL

BREVO_SMTP_URL = "https://api.brevo.com/v3/smtp/email"


def enviar_correo_reset(correo_destino: str, token: str, username: str = "usuario") -> bool:
    """
    Envía un correo de recuperación de contraseña con el link de reset.

    Args:
        correo_destino: Email del usuario que solicitó el reset.
        token:          Token seguro de un solo uso (expira en 1 hora).
        username:       Nombre del usuario (para personalizar el mensaje).

    Returns:
        True si el email fue enviado correctamente, False si falló.
    """
    if not BREVO_API_KEY:
        print("  ⚠️  BREVO_API_KEY no configurada. El correo no fue enviado.")
        return False

    reset_url = f"{SERVER_BASE_URL}/auth/reset-password?token={token}"

    html_content = f"""
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Recupera tu contraseña - TapoMon</title>
</head>
<body style="margin:0;padding:0;background:#0a0a14;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a14;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="520" cellpadding="0" cellspacing="0"
               style="background:#12121f;border-radius:16px;border:1px solid #2a2a3e;overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#3b5bdb,#7c3aed);padding:36px 40px;text-align:center;">
              <div style="font-size:36px;margin-bottom:8px;">🐾</div>
              <h1 style="margin:0;color:#ffffff;font-size:26px;font-weight:700;letter-spacing:1px;">
                TapoMon
              </h1>
              <p style="margin:6px 0 0;color:#c7d2fe;font-size:13px;">Tu mascota virtual distribuida</p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 40px;">
              <h2 style="color:#e2e8f0;font-size:20px;margin:0 0 12px;">
                Hola, {username} 👋
              </h2>
              <p style="color:#94a3b8;font-size:15px;line-height:1.6;margin:0 0 20px;">
                Recibimos una solicitud para restablecer la contraseña de tu cuenta de TapoMon.
                Si no fuiste tú, puedes ignorar este correo.
              </p>
              <p style="color:#94a3b8;font-size:15px;line-height:1.6;margin:0 0 28px;">
                El enlace es válido por <strong style="color:#e2e8f0;">1 hora</strong>.
              </p>

              <!-- CTA Button -->
              <div style="text-align:center;margin-bottom:32px;">
                <a href="{reset_url}"
                   style="display:inline-block;background:linear-gradient(135deg,#3b5bdb,#7c3aed);
                          color:#ffffff;font-size:16px;font-weight:600;text-decoration:none;
                          padding:14px 36px;border-radius:8px;letter-spacing:0.5px;">
                  🔑 Restablecer contraseña
                </a>
              </div>

              <!-- Fallback link -->
              <p style="color:#64748b;font-size:12px;line-height:1.6;margin:0 0 8px;">
                Si el botón no funciona, copia y pega este enlace en tu navegador:
              </p>
              <p style="margin:0;">
                <a href="{reset_url}"
                   style="color:#818cf8;font-size:12px;word-break:break-all;">
                  {reset_url}
                </a>
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#0d0d1a;padding:20px 40px;border-top:1px solid #1e1e2e;text-align:center;">
              <p style="color:#475569;font-size:12px;margin:0;">
                © 2026 TapoMon — Sistema de mascotas virtuales distribuidas<br>
                Este correo fue generado automáticamente. No respondas a este mensaje.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    payload = {
        "sender": {
            "name":  BREVO_SENDER_NAME,
            "email": BREVO_SENDER_EMAIL,
        },
        "to": [{"email": correo_destino}],
        "subject": "🔑 Restablece tu contraseña de TapoMon",
        "htmlContent": html_content,
    }

    headers = {
        "accept":       "application/json",
        "content-type": "application/json",
        "api-key":      BREVO_API_KEY,
    }

    try:
        resp = requests.post(BREVO_SMTP_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code in (200, 201, 202):
            print(f"  ✅  Correo de reset enviado a {correo_destino}")
            return True
        else:
            print(f"  ⚠️  Brevo error {resp.status_code}: {resp.text}")
            return False
    except requests.RequestException as e:
        print(f"  ⚠️  Error al contactar Brevo: {e}")
        return False


def enviar_codigo_2fa(correo_destino: str, codigo: str, username: str = "usuario") -> bool:
    """
    Envía un correo con el código de verificación de 6 dígitos para 2FA.

    Args:
        correo_destino: Email del usuario que está iniciando sesión.
        codigo:         Código de 6 dígitos generado aleatoriamente.
        username:       Nombre del usuario (para personalizar el mensaje).

    Returns:
        True si el email fue enviado correctamente, False si falló.
    """
    if not BREVO_API_KEY:
        print(f"  ⚠️  BREVO_API_KEY no configurada. Código 2FA: {codigo}")
        return False

    html_content = f"""
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Código de verificación - TapoMon</title>
</head>
<body style="margin:0;padding:0;background:#0a0a14;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a14;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="520" cellpadding="0" cellspacing="0"
               style="background:#12121f;border-radius:16px;border:1px solid #2a2a3e;overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#3b5bdb,#7c3aed);padding:36px 40px;text-align:center;">
              <div style="font-size:36px;margin-bottom:8px;">🛡️</div>
              <h1 style="margin:0;color:#ffffff;font-size:26px;font-weight:700;letter-spacing:1px;">
                TapoMon
              </h1>
              <p style="margin:6px 0 0;color:#c7d2fe;font-size:13px;">Verificación de dos pasos</p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 40px;text-align:center;">
              <h2 style="color:#e2e8f0;font-size:20px;margin:0 0 8px;">
                Hola, {username} 👋
              </h2>
              <p style="color:#94a3b8;font-size:15px;line-height:1.6;margin:0 0 28px;">
                Alguien está intentando iniciar sesión en tu cuenta de TapoMon.<br>
                Usa el siguiente código para completar el acceso:
              </p>

              <!-- Code box -->
              <div style="background:#1e1e2e;border:2px solid #7c3aed;border-radius:12px;
                          padding:24px 32px;margin:0 auto 28px;display:inline-block;">
                <span style="font-size:42px;font-weight:800;letter-spacing:14px;
                             color:#818cf8;font-family:monospace;">
                  {codigo}
                </span>
              </div>

              <p style="color:#94a3b8;font-size:14px;line-height:1.6;margin:0 0 8px;">
                ⏱️ Este código expira en <strong style="color:#e2e8f0;">10 minutos</strong>.
              </p>
              <p style="color:#64748b;font-size:13px;margin:0;">
                Si no fuiste tú, ignora este correo. Tu cuenta sigue segura.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#0d0d1a;padding:20px 40px;border-top:1px solid #1e1e2e;text-align:center;">
              <p style="color:#475569;font-size:12px;margin:0;">
                © 2026 TapoMon — Sistema de mascotas virtuales distribuidas<br>
                Este correo fue generado automáticamente. No respondas a este mensaje.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    payload = {
        "sender": {
            "name":  BREVO_SENDER_NAME,
            "email": BREVO_SENDER_EMAIL,
        },
        "to": [{"email": correo_destino}],
        "subject": f"🛡️ Tu código de verificación TapoMon: {codigo}",
        "htmlContent": html_content,
    }

    headers = {
        "accept":       "application/json",
        "content-type": "application/json",
        "api-key":      BREVO_API_KEY,
    }

    try:
        resp = requests.post(BREVO_SMTP_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code in (200, 201, 202):
            print(f"  ✅  Código 2FA enviado a {correo_destino}")
            return True
        else:
            print(f"  ⚠️  Brevo error {resp.status_code}: {resp.text}")
            return False
    except requests.RequestException as e:
        print(f"  ⚠️  Error al contactar Brevo: {e}")
        return False
