"""Tool implementations for system-level operations (volume, brightness, wifi, etc.)."""

import asyncio
import os
from datetime import datetime
from pathlib import Path

from loguru import logger


async def set_volume(level: int) -> dict:
    """Ajusta el volumen del sistema al nivel especificado (0-100). Implemented.

    Args:
        level: Nivel de volumen entre 0 y 100.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"set_volume called with level={level}")
    try:
        level = max(0, min(100, level))
        wpctl_level = level / 100
        proc = await asyncio.create_subprocess_exec(
            "wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{wpctl_level:.2f}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error(f"set_volume failed: {err}")
            return {"success": False, "result": None, "error": err}
        logger.info(f"Volume set to {level}%")
        return {"success": True, "result": {"level": level}, "error": None}
    except Exception as e:
        logger.exception("set_volume error")
        return {"success": False, "result": None, "error": str(e)}


async def set_brightness(level: int) -> dict:
    """Ajusta el brillo de la pantalla al nivel especificado (0-100). Implemented.

    Args:
        level: Nivel de brillo entre 0 y 100.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"set_brightness called with level={level}")
    try:
        level = max(0, min(100, level))
        proc = await asyncio.create_subprocess_exec(
            "brightnessctl", "set", f"{level}%",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error(f"set_brightness failed: {err}")
            return {"success": False, "result": None, "error": err}
        logger.info(f"Brightness set to {level}%")
        return {"success": True, "result": {"level": level}, "error": None}
    except Exception as e:
        logger.exception("set_brightness error")
        return {"success": False, "result": None, "error": str(e)}


async def get_wifi_status() -> dict:
    """Obtiene el estado actual de la conexión WiFi. Implemented.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: connected (bool), ssid (str | None), signal (int | None).
    """
    logger.debug("get_wifi_status called")
    try:
        proc = await asyncio.create_subprocess_exec(
            "nmcli", "-t", "-f", "active,ssid,signal", "dev", "wifi",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error(f"get_wifi_status failed: {err}")
            return {"success": False, "result": None, "error": err}

        output = stdout.decode().strip()
        connected = False
        ssid = None
        signal = None

        for line in output.splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[0] == "yes":
                connected = True
                ssid = parts[1] if parts[1] else None
                try:
                    signal = int(parts[2])
                except ValueError:
                    signal = None
                break

        result = {"connected": connected, "ssid": ssid, "signal": signal}
        logger.info(f"WiFi status: {result}")
        return {"success": True, "result": result, "error": None}
    except Exception as e:
        logger.exception("get_wifi_status error")
        return {"success": False, "result": None, "error": str(e)}


async def toggle_wifi() -> dict:
    """Activa o desactiva el WiFi según su estado actual. Implemented.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: enabled (bool).
    """
    logger.debug("toggle_wifi called")
    try:
        # Check current state
        check_proc = await asyncio.create_subprocess_exec(
            "nmcli", "radio", "wifi",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await check_proc.communicate()
        if check_proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error(f"toggle_wifi check failed: {err}")
            return {"success": False, "result": None, "error": err}

        current_state = stdout.decode().strip().lower()
        currently_enabled = current_state == "enabled"
        new_state = "off" if currently_enabled else "on"

        toggle_proc = await asyncio.create_subprocess_exec(
            "nmcli", "radio", "wifi", new_state,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await toggle_proc.communicate()
        if toggle_proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error(f"toggle_wifi set failed: {err}")
            return {"success": False, "result": None, "error": err}

        enabled = not currently_enabled
        logger.info(f"WiFi toggled to: {'enabled' if enabled else 'disabled'}")
        return {"success": True, "result": {"enabled": enabled}, "error": None}
    except Exception as e:
        logger.exception("toggle_wifi error")
        return {"success": False, "result": None, "error": str(e)}


async def get_system_info() -> dict:
    """Obtiene información general del sistema (CPU, RAM, disco, etc.). Implemented.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: cpu_load, ram_used, ram_total, ram_percent, disk_used,
                        disk_total, disk_percent, uptime.
    """
    logger.debug("get_system_info called")
    try:
        # CPU load from /proc/loadavg
        loadavg_path = Path("/proc/loadavg")
        loadavg = loadavg_path.read_text().split()
        cpu_load_1m = float(loadavg[0])

        # RAM from /proc/meminfo
        meminfo_path = Path("/proc/meminfo")
        meminfo = {}
        for line in meminfo_path.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                key = parts[0].rstrip(":")
                value_kb = int(parts[1])
                meminfo[key] = value_kb

        mem_total_kb = meminfo.get("MemTotal", 0)
        mem_available_kb = meminfo.get("MemAvailable", 0)
        mem_used_kb = mem_total_kb - mem_available_kb
        mem_total_gb = mem_total_kb / (1024 ** 2)
        mem_used_gb = mem_used_kb / (1024 ** 2)
        mem_percent = (mem_used_kb / mem_total_kb * 100) if mem_total_kb else 0

        # Disk from df
        df_proc = await asyncio.create_subprocess_exec(
            "df", "-h", "/",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        df_stdout, _ = await df_proc.communicate()
        disk_used = "N/A"
        disk_total = "N/A"
        disk_percent = "N/A"
        df_lines = df_stdout.decode().strip().splitlines()
        if len(df_lines) >= 2:
            df_parts = df_lines[1].split()
            if len(df_parts) >= 5:
                disk_total = df_parts[1]
                disk_used = df_parts[2]
                disk_percent = df_parts[4]

        # Uptime from /proc/uptime
        uptime_path = Path("/proc/uptime")
        uptime_seconds = float(uptime_path.read_text().split()[0])
        uptime_hours = int(uptime_seconds // 3600)
        uptime_minutes = int((uptime_seconds % 3600) // 60)
        uptime_str = f"{uptime_hours}h {uptime_minutes}m"

        result = {
            "cpu_load_1m": round(cpu_load_1m, 2),
            "ram_used": f"{mem_used_gb:.1f} GB",
            "ram_total": f"{mem_total_gb:.1f} GB",
            "ram_display": f"{mem_used_gb:.1f} GB / {mem_total_gb:.1f} GB",
            "ram_percent": round(mem_percent, 1),
            "disk_used": disk_used,
            "disk_total": disk_total,
            "disk_percent": disk_percent,
            "uptime": uptime_str,
        }
        logger.info(f"System info: {result}")
        return {"success": True, "result": result, "error": None}
    except Exception as e:
        logger.exception("get_system_info error")
        return {"success": False, "result": None, "error": str(e)}


async def take_screenshot() -> dict:
    """Toma una captura de pantalla y la guarda en el directorio de imágenes. Implemented.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: path (str) con la ruta al archivo guardado.
    """
    logger.debug("take_screenshot called")
    try:
        pictures_dir = Path.home() / "Pictures"
        pictures_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_path = pictures_dir / f"screenshot-{timestamp}.png"

        proc = await asyncio.create_subprocess_exec(
            "grim", str(output_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error(f"take_screenshot failed: {err}")
            return {"success": False, "result": None, "error": err}

        logger.info(f"Screenshot saved to {output_path}")
        return {"success": True, "result": {"path": str(output_path)}, "error": None}
    except Exception as e:
        logger.exception("take_screenshot error")
        return {"success": False, "result": None, "error": str(e)}


async def shutdown() -> dict:
    """Apaga el sistema de forma segura. Implemented.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug("shutdown called")
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "poweroff",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error(f"shutdown failed: {err}")
            return {"success": False, "result": None, "error": err}
        logger.info("System shutdown initiated")
        return {"success": True, "result": {"message": "Shutdown initiated"}, "error": None}
    except Exception as e:
        logger.exception("shutdown error")
        return {"success": False, "result": None, "error": str(e)}


async def reboot() -> dict:
    """Reinicia el sistema de forma segura. Implemented.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug("reboot called")
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "reboot",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error(f"reboot failed: {err}")
            return {"success": False, "result": None, "error": err}
        logger.info("System reboot initiated")
        return {"success": True, "result": {"message": "Reboot initiated"}, "error": None}
    except Exception as e:
        logger.exception("reboot error")
        return {"success": False, "result": None, "error": str(e)}


async def lock_screen() -> dict:
    """Bloquea la pantalla del sistema. Implemented.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug("lock_screen called")
    try:
        proc = await asyncio.create_subprocess_exec(
            "hyprlock",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # Don't wait — hyprlock blocks until unlocked; fire and forget
        logger.info("Screen lock initiated")
        return {"success": True, "result": {"message": "Screen locked"}, "error": None}
    except Exception as e:
        logger.exception("lock_screen error")
        return {"success": False, "result": None, "error": str(e)}
