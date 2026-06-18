import json
import struct
import asyncio

from utils.config import MINECRAFT_PROTOCOL_VERSION


async def get_minecraft_ping_status(host: str, port: int = 25565) -> dict:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=2.0
        )

        def write_varint(val: int) -> bytes:
            out = b""
            while True:
                b = val & 0x7F
                val >>= 7
                if val:
                    out += struct.pack("B", b | 0x80)
                else:
                    out += struct.pack("B", b)
                    break
            return out

        async def read_varint() -> int:
            val = 0
            for i in range(5):
                b = await reader.readexactly(1)
                if not b:
                    return 0
                b = b[0]
                val |= (b & 0x7F) << (7 * i)
                if not (b & 0x80):
                    break
            return val

        host_bytes = host.encode('utf-8')
        handshake = (
            write_varint(0)
            + write_varint(MINECRAFT_PROTOCOL_VERSION)
            + write_varint(len(host_bytes))
            + host_bytes
            + struct.pack(">H", port)
            + write_varint(1)
        )
        writer.write(write_varint(len(handshake)) + handshake)
        await writer.drain()

        request = write_varint(0)
        writer.write(write_varint(len(request)) + request)
        await writer.drain()

        packet_len = await read_varint()
        packet_id = await read_varint()
        json_len = await read_varint()

        data = await reader.readexactly(json_len)
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass

        info = json.loads(data.decode('utf-8'))
        version_name = info.get("version", {}).get("name", "")
        max_players = info.get("players", {}).get("max", 0)
        online_count = info.get("players", {}).get("online", 0)

        return {
            "status": "success",
            "version_name": version_name,
            "online_count": online_count,
            "max_players": max_players,
            "info": info,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
