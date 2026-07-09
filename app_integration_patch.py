
"""
Fragmenty do dopięcia w app.py.

1) Na starcie aplikacji dodaj:
from position_store import init_position_db, evaluate_positions
from telegram_position_commands import handle_position_command

init_position_db()

2) W miejscu, gdzie odbierasz wiadomości Telegram, dodaj:
reply = handle_position_command(message_text)
if reply:
    send_telegram_message(reply)
    return

3) W miejscu, gdzie bot ma aktualną cenę XAU/USD, dodaj:
position_alerts = evaluate_positions(current_price)
for alert in position_alerts:
    send_telegram_message(alert)

4) Gdy bot sam generuje sygnał BUY/SELL, po wysłaniu sygnału dodaj:
from position_store import add_position

if signal in ("BUY", "SELL"):
    add_position(
        side=signal,
        entry=entry,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        source="bot_signal",
        note=f"score={score}; setup={setup}; regime={regime}"
    )
""".strip()
