"""
Wklej/importuj do app.py, gdzie obsługujesz wiadomości Telegram.
Komendy:
 /position SELL 4124.55 4202.03 3969.59 3892.11 3814.63
 /position BUY 4100 4070 4130 4160 4200
 /positions
 /close POSITION_ID
"""

from position_store import add_position, format_positions, close_position


def handle_position_command(text):
    parts = text.strip().split()
    cmd = parts[0].lower()

    if cmd == "/position":
        if len(parts) < 4:
            return (
                "Użycie:\n"
                "/position SELL entry sl tp1 tp2 tp3\n"
                "Przykład:\n"
                "/position SELL 4124.55 4202.03 3969.59 3892.11 3814.63"
            )

        side = parts[1].upper()
        entry = float(parts[2])
        sl = float(parts[3]) if len(parts) > 3 and parts[3] != "-" else None
        tp1 = float(parts[4]) if len(parts) > 4 and parts[4] != "-" else None
        tp2 = float(parts[5]) if len(parts) > 5 and parts[5] != "-" else None
        tp3 = float(parts[6]) if len(parts) > 6 and parts[6] != "-" else None

        p = add_position(side=side, entry=entry, sl=sl, tp1=tp1, tp2=tp2, tp3=tp3)
        return (
            f"✅ Pozycja zapisana w pamięci bota\n"
            f"ID: {p['id']}\n"
            f"{side} XAU/USD\nEntry: {entry}\nSL: {sl}\nTP1: {tp1} | TP2: {tp2} | TP3: {tp3}"
        )

    if cmd == "/positions":
        return format_positions()

    if cmd == "/close":
        if len(parts) < 2:
            return "Użycie: /close POSITION_ID"
        close_position(parts[1], "closed from Telegram")
        return f"✅ Pozycja zamknięta w pamięci bota: {parts[1]}"

    return None