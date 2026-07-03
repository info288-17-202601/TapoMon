"""
server/api/auth_routes.py
Endpoints de autenticación del servidor central.

Justificación:
    El informe requiere protección de procesos y canales:
    "Para evitar que un atacante suplante la identidad de un usuario
     y altere las estadísticas de una mascota ajena, se establecen
     procesos de autenticación en el servidor central."

    Este módulo expone:
    - POST /auth/login            → Retorna un JWT si las credenciales son válidas.
    - POST /auth/forgot-password  → Envía email con link de reset.
    - GET  /auth/reset-password   → Sirve la página HTML de reset.
    - POST /auth/reset-password   → Procesa el nuevo password.
    - Dependency get_current_user → Extrae y valida el JWT de cada request.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional

from server.models.schemas import (
    LoginRequest, TokenResponse, ErrorResponse,
    RegisterRequest, ForgotPasswordRequest, ResetPasswordRequest,
    LoginChallengeResponse, TwoFactorVerifyRequest,
)
from server.services.auth_service import (
    autenticar_usuario,
    generar_token,
    verificar_token,
    registrar_usuario,
    crear_token_reset,
    resetear_password,
    crear_sesion_2fa,
    verificar_2fa_codigo,
)
from server.services.email_service import enviar_correo_reset, enviar_codigo_2fa

router = APIRouter()


# ------------------------------------------------------------------ #
#  Dependency: Extraer usuario autenticado del token
# ------------------------------------------------------------------ #

async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """
    FastAPI Dependency que valida el JWT en el header Authorization.
    Uso: cualquier endpoint protegido recibe este dependency.
    
    Header esperado: Authorization: Bearer <token>
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Token no proporcionado.")

    # Extraer token del header "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Formato de token inválido. Usar: Bearer <token>")

    token = parts[1]
    payload = verificar_token(token)

    if payload is None:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")

    return payload


# ------------------------------------------------------------------ #
#  Endpoints
# ------------------------------------------------------------------ #

@router.post("/login", response_model=LoginChallengeResponse, tags=["Autenticación"])
async def login(request: LoginRequest):
    """
    Autentica las credenciales del usuario.

    Con 2FA activo NO retorna el JWT directamente. En cambio:
    1. Valida username/password.
    2. Genera un código de 6 dígitos válido 10 minutos.
    3. Lo envía al correo registrado.
    4. Retorna session_id + correo_hint para que el cliente solicite el código.

    El JWT se obtiene luego en POST /auth/verify-2fa.
    """
    usuario_doc = autenticar_usuario(request.username, request.password)

    if usuario_doc is None:
        raise HTTPException(
            status_code=401,
            detail="Usuario o contraseña incorrectos."
        )

    # Generar sesión 2FA y enviar código
    session_id, codigo, correo_hint = crear_sesion_2fa(usuario_doc)
    enviar_codigo_2fa(
        correo_destino=usuario_doc["Correo"],
        codigo=codigo,
        username=usuario_doc.get("Username", "usuario"),
    )

    return LoginChallengeResponse(
        requires_2fa=True,
        session_id=session_id,
        correo_hint=correo_hint,
    )


@router.post("/verify-2fa", response_model=TokenResponse, tags=["Autenticación"])
async def verify_2fa(request: TwoFactorVerifyRequest):
    """
    Verifica el código 2FA y entrega el JWT.

    Recibe el session_id del challenge y el código de 6 dígitos
    que el usuario ingresó desde su correo.
    """
    usuario_doc = verificar_2fa_codigo(request.session_id, request.codigo)

    if usuario_doc is None:
        raise HTTPException(
            status_code=401,
            detail="Código incorrecto o expirado. Vuelve a iniciar sesión."
        )

    token = generar_token(usuario_doc)

    return TokenResponse(
        access_token=token,
        usuario_id=usuario_doc["Id"],
        username=usuario_doc["Username"],
        correo=usuario_doc["Correo"],
        tapo_id=usuario_doc["Tapo_ID"],
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(request: RegisterRequest):
    """
    Registra un usuario nuevo en el servidor y retorna un JWT.

    El cliente genera los UUIDs (usuario_id, tapo_id) para garantizar
    que ambas bases de datos (local y servidor) usen los mismos IDs.

    Retorna 409 si el username ya está registrado en el servidor.
    Retorna 201 + JWT si el registro fue exitoso.
    """
    usuario_doc, error_msg = registrar_usuario(
        username=request.username,
        correo=request.correo,
        password=request.password,
        usuario_id=request.usuario_id,
        tapo_id=request.tapo_id,
    )

    if usuario_doc is None:
        raise HTTPException(
            status_code=409,
            detail=error_msg or "Error al registrar el usuario."
        )

    token = generar_token(usuario_doc)

    return TokenResponse(
        access_token=token,
        usuario_id=usuario_doc["Id"],
        username=usuario_doc["Username"],
        correo=usuario_doc["Correo"],
        tapo_id=usuario_doc["Tapo_ID"],
    )


# ------------------------------------------------------------------ #
#  Recuperación de contraseña
# ------------------------------------------------------------------ #

@router.post("/forgot-password", tags=["Autenticación"])
async def forgot_password(request: ForgotPasswordRequest):
    """
    Solicita el envío de un correo de recuperación de contraseña.

    Por seguridad, siempre responde con el mismo mensaje exitoso
    independientemente de si el correo existe o no (evita enumeración).
    """
    resultado = crear_token_reset(request.correo)
    if resultado is not None:
        token, username = resultado
        enviar_correo_reset(request.correo, token, username)
    # Respuesta genérica siempre (no revelar si el correo existe)
    return {"message": "Si el correo está registrado, recibirás un enlace de recuperación en breve."}


@router.get("/reset-password", response_class=HTMLResponse, tags=["Autenticación"])
async def reset_password_page(token: str):
    """
    Sirve la página HTML donde el usuario ingresa su nueva contraseña.
    El token viene como query param: /auth/reset-password?token=<tok>
    """
    html = f"""
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Restablecer contraseña — TapoMon</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #0a0a14;
      font-family: 'Inter', sans-serif;
      padding: 24px;
    }}
    .dots-bg {{
      position: fixed; inset: 0; z-index: 0;
      background-image: radial-gradient(circle, #2a2a3e 1px, transparent 1px);
      background-size: 36px 36px;
      opacity: 0.5;
    }}
    .card {{
      position: relative; z-index: 1;
      background: #12121f;
      border: 1px solid #2a2a3e;
      border-radius: 20px;
      padding: 48px 40px;
      width: 100%;
      max-width: 440px;
      box-shadow: 0 24px 64px rgba(0,0,0,.6), 0 0 0 1px rgba(124,58,237,.1);
    }}
    .logo {{ text-align: center; margin-bottom: 32px; }}
    .logo-icon {{ font-size: 48px; display: block; margin-bottom: 10px; }}
    .logo h1 {{
      font-size: 28px; font-weight: 700;
      background: linear-gradient(135deg, #818cf8, #a78bfa);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      background-clip: text;
    }}
    .logo p {{ color: #64748b; font-size: 13px; margin-top: 4px; }}
    label {{
      display: block;
      color: #94a3b8;
      font-size: 13px;
      font-weight: 500;
      margin-bottom: 6px;
      margin-top: 20px;
    }}
    input[type=password] {{
      width: 100%;
      background: #1e1e2e;
      border: 1px solid #2a2a3e;
      border-radius: 10px;
      padding: 12px 16px;
      color: #e2e8f0;
      font-size: 15px;
      font-family: inherit;
      outline: none;
      transition: border-color .2s, box-shadow .2s;
    }}
    input[type=password]:focus {{
      border-color: #7c3aed;
      box-shadow: 0 0 0 3px rgba(124,58,237,.15);
    }}
    .hint {{ color: #475569; font-size: 12px; margin-top: 6px; }}
    button {{
      width: 100%;
      margin-top: 28px;
      padding: 14px;
      border: none;
      border-radius: 10px;
      background: linear-gradient(135deg, #3b5bdb, #7c3aed);
      color: #fff;
      font-size: 16px;
      font-weight: 600;
      font-family: inherit;
      cursor: pointer;
      transition: opacity .2s, transform .15s;
    }}
    button:hover {{ opacity: .9; transform: translateY(-1px); }}
    button:active {{ transform: translateY(0); }}
    button:disabled {{ opacity: .5; cursor: not-allowed; transform: none; }}
    #msg {{
      margin-top: 20px;
      padding: 14px 16px;
      border-radius: 10px;
      font-size: 14px;
      display: none;
      text-align: center;
      line-height: 1.5;
    }}
    #msg.ok  {{ background: rgba(34,197,94,.1);  border:1px solid rgba(34,197,94,.3);  color:#86efac; }}
    #msg.err {{ background: rgba(239,68,68,.1);  border:1px solid rgba(239,68,68,.3);  color:#fca5a5; }}
    .divider {{ border: none; border-top: 1px solid #1e1e2e; margin: 28px 0 0; }}
  </style>
</head>
<body>
  <div class="dots-bg"></div>
  <div class="card">
    <div class="logo">
      <span class="logo-icon">🐾</span>
      <h1>TapoMon</h1>
      <p>Restablece tu contraseña</p>
    </div>

    <form id="resetForm">
      <label for="pass1">Nueva contraseña</label>
      <input type="password" id="pass1" placeholder="Mínimo 6 caracteres" autocomplete="new-password" required>

      <label for="pass2">Confirmar contraseña</label>
      <input type="password" id="pass2" placeholder="Repite la contraseña" autocomplete="new-password" required>
      <p class="hint">Ambas contraseñas deben coincidir.</p>

      <button type="submit" id="btn">🔑 Cambiar contraseña</button>
    </form>

    <div id="msg"></div>
    <hr class="divider">
  </div>

  <script>
    const TOKEN = "{token}";
    const form  = document.getElementById('resetForm');
    const btn   = document.getElementById('btn');
    const msg   = document.getElementById('msg');

    function showMsg(text, ok) {{
      msg.textContent = text;
      msg.className   = ok ? 'ok' : 'err';
      msg.style.display = 'block';
    }}

    form.addEventListener('submit', async (e) => {{
      e.preventDefault();
      const p1 = document.getElementById('pass1').value;
      const p2 = document.getElementById('pass2').value;

      if (p1.length < 6) {{ showMsg('La contraseña debe tener al menos 6 caracteres.', false); return; }}
      if (p1 !== p2)     {{ showMsg('Las contraseñas no coinciden.', false); return; }}

      btn.disabled    = true;
      btn.textContent = 'Procesando...';

      const urlParams = new URLSearchParams(window.location.search);
      const region = urlParams.get('region') || '';

      try {{
        const res = await fetch(`/auth/reset-password?region=${{region}}`, {{
          method:  'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body:    JSON.stringify({{ token: TOKEN, nueva_password: p1 }}),
        }});
        const data = await res.json();
        if (res.ok && data.success) {{
          showMsg('✅ ¡Contraseña actualizada! Ya puedes iniciar sesión en TapoMon.', true);
          form.style.display = 'none';
        }} else {{
          showMsg(data.detail || data.message || 'Error al procesar la solicitud.', false);
          btn.disabled    = false;
          btn.textContent = '🔑 Cambiar contraseña';
        }}
      }} catch (err) {{
        showMsg('Error de conexión. Inténtalo de nuevo.', false);
        btn.disabled    = false;
        btn.textContent = '🔑 Cambiar contraseña';
      }}
    }});
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html)


@router.post("/reset-password", tags=["Autenticación"])
async def reset_password(request: ResetPasswordRequest):
    """
    Procesa el formulario de reset: valida el token y actualiza la contraseña.
    Llamado desde el JavaScript de la página /auth/reset-password.
    """
    if len(request.nueva_password) < 6:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres.")

    ok = resetear_password(request.token, request.nueva_password)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="El enlace de recuperación es inválido o ha expirado. Solicita uno nuevo."
        )

    return {"success": True, "message": "Contraseña actualizada correctamente."}
