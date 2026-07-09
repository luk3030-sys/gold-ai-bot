"""
Przykładowy minimalny fragment do wklejenia w app.py.

Użyj tego tylko jako wzoru, bo dokładne miejsce zależy od Twojego aktualnego kodu.
"""

from position_manager import handle_position_message


def process_telegram_message(message):
    text = message.get("text", "")

    # Przekaż ATR H1, jeśli bot go już obliczył.
    # Zmień `atr_h1` na nazwę zmiennej z Twojego kodu.
    market_state = {
        "atr_h1": globals().get("atr_h1", 12.0)
    }

    position_reply = handle_position_message(text, market_state=market_state)
    if position_reply:
        send_telegram_message(position_reply)
        return

    # tutaj zostaje dotychczasowa logika bota
