"""Create refund claims for the two FC26 items with inaccessible login data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lzt import api_call

CLAIM_BODY = (
    "Здравствуйте. После покупки лота данные для входа в аккаунт "
    "недоступны: в карточке покупки и в выгрузке купленных аккаунтов "
    "(api.lzt.market/user/orders/download) поле с паролем аккаунта пустое, "
    "флаг canViewLoginData = false. Вход по паролю от приложенной почты "
    "не проходит. Прошу предоставить корректные данные для входа "
    "(логин:пароль аккаунта) либо оформить возврат средств. "
    "Заранее спасибо."
)


def main() -> None:
    for iid in (258553032, 258552493):
        try:
            res = api_call("POST", "/claims",
                           data={"item_id": iid, "post_body": CLAIM_BODY})
            thread = res.get("thread", {})
            print(f"{iid}: claim created -> "
                  f"thread {thread.get('thread_id')} "
                  f"{thread.get('links', {}).get('permalink', '')}")
        except RuntimeError as e:
            print(f"{iid}: FAILED: {str(e)[:250]}")


if __name__ == "__main__":
    main()
