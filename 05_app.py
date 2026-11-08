#!/usr/bin/env python3
"""
CLI-прототип платёжного сервиса — кейс 1.
"""

import csv          # Для работы с CSV-файлами (чтение справочников и запись результатов)
import hashlib      # Для создания детерминированного хэша (эмулятор шлюза)
import json         # Для чтения входящего JSON и вывода ответа
import os           # Для работы с путями к файлам
import re           # Для регулярных выражений (проверка формата order_id и поиск PAN)
import sys          # Для получения аргументов командной строки и exit-кодов
from datetime import datetime       # Для записи времени создания/подтверждения

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECIPIENTS_CSV = os.path.join(BASE_DIR, "recipients.csv")
OUT_CSV = os.path.join(BASE_DIR, "payments_out.csv")

# V-2: order_id должен состоять из латиницы, цифр, дефисов и подчеркиваний (1-64 символа)
ORDER_ID_RE = re.compile(r'^[A-Za-z0-9_\-]{1,64}$')

# V-6: PAN-номер (номер банковской карты) — это 13-19 цифр подряд. Их нельзя писать в назначение!
PAN_RE = re.compile(r'\d{13,19}')


def load_active_recipients():
    """
    Загружает список активных клиник/получателей из recipients.csv.
    Возвращает set (множество), чтобы поиск был мгновенным.
    """
    active = set()
    try:
        # Открываем файл.
        with open(RECIPIENTS_CSV, encoding="cp1251") as f:
            for row in csv.DictReader(f):
                # V-5: Берем только тех получателей, у кого статус ACTIVE (игнорируем INACTIVE, BLOCKED)
                if row.get("status") == "ACTIVE":
                    active.add(row["recipient_id"])
    except FileNotFoundError:
        # Если файла нет — выводим предупреждение, но программа продолжает работу
        print(f"WARN: {RECIPIENTS_CSV} не найден", file=sys.stderr)
    return active

def load_existing_payments(path):
    """
    Читает payments_out.csv (базу платежей), чтобы проверить дубликаты.
    Возвращает:
      existing_orders — множество пар (order_id, recipient) для правила V-8
      seen_idem — словарь (ключ -> строка) для проверки идемпотентности V-9
    """
    existing_orders = set()
    seen_idem = {}
    try:
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                # Сохраняем связку "номер заказа + получатель" для поиска дублей
                existing_orders.add((row.get("order_id"), row.get("recipient")))
                # V-9: Сохраняем ключ идемпотентности и ВСЮ строку ответа
                key = row.get("idempotency_key")
                if key:
                    seen_idem[key] = row
    except FileNotFoundError:
        # Если файла еще нет — это первый запуск, всё нормально
        pass  
    return existing_orders, seen_idem

def validate(payload, active_recipients, existing_orders=None, seen_idempotency=None):
    """
    Главная функция проверки данных (Валидация).
    Реализует правила V-1...V-9 из 02_правила.md.
    Возвращает список ошибок [(поле, код_ошибки), ...]. Если пусто — ошибок нет.
    """
    errors = []

    # ---------- V-1: обязательные поля ----------
    # Если какое-то из этих полей пустое (None, "" или []), добавляем ошибку
    for field in ["order_id", "recipient", "purpose", "amount", "currency"]:
        if payload.get(field) in (None, "", []):
            errors.append((field, "VALIDATION_ERROR"))
    if errors:
        # без обязательных полей дальше проверять нечего
        return errors

    # ---------- V-2: формат order_id ----------
    # Проверяем, соответствует ли order_id регулярному выражению (без пробелов и спецсимволов)
    if not ORDER_ID_RE.match(str(payload["order_id"])):
        errors.append(("order_id", "INVALID_FORMAT"))

    # ---------- V-3: диапазон суммы ----------
    amt = None
    try:
        # Пытаемся превратить сумму в число с плавающей точкой
        amt = float(payload["amount"])
    except (TypeError, ValueError):
        # Если пришла строка "abc" или None — это ошибка
        errors.append(("amount", "AMOUNT_OUT_OF_RANGE"))
    # Сумма должна быть строго больше 0 и не превышать 1 000 000
    if amt is not None and (amt <= 0 or amt > 1_000_000):
        errors.append(("amount", "AMOUNT_OUT_OF_RANGE"))

    # ---------- V-4: валюта ----------
    # В нашем сервисе разрешен только RUB
    if payload["currency"] not in ("RUB",):
        errors.append(("currency", "UNSUPPORTED_CURRENCY"))

    # ---------- V-5: получатель активен ----------
    # Проверяем, есть ли получатель в списке активных (из recipients.csv)
    if payload["recipient"] not in active_recipients:
        errors.append(("recipient", "RECIPIENT_NOT_FOUND"))

    # ---------- V-6: purpose (длина + PAN) ----------
    purpose = str(payload["purpose"])
    # Если длина больше 200 ИЛИ внутри есть номер карты (PAN_RE) — ошибка
    if len(purpose) > 200 or PAN_RE.search(purpose):
        errors.append(("purpose", "INVALID_PURPOSE"))

    # ---------- V-7: точность суммы (≤ 2 знака) ----------
    raw_amount = str(payload["amount"])
    if "." in raw_amount:
        decimals = raw_amount.split(".", 1)[1]
        if len(decimals) > 2:
            errors.append(("amount", "INVALID_AMOUNT_PRECISION"))

    # ---------- V-8: дубль order_id + recipient ----------
    # Если такая пара (order_id + recipient) уже есть в базе — не создаем новый платеж
    if existing_orders and (payload["order_id"], payload["recipient"]) in existing_orders:
        errors.append(("order_id", "DUPLICATE_ORDER"))

    # ---------- V-9: повтор Idempotency-Key ----------
    # Если этот Idempotency-Key уже использовался, помечаем это специальным кодом
    key = payload.get("idempotency_key")
    if seen_idempotency is not None and key and key in seen_idempotency:
        errors.append(("idempotency_key", "DUPLICATE_REQUEST"))

    return errors

def emulate_gateway(order_id):
    """
    4 сценария. Возвращает (status, error_code).
    hash(order_id) mod 10:
      0..6 — SUCCESS
      7    — DECLINED / INSUFFICIENT_FUNDS
      8    — DECLINED / CARD_DECLINED
      9    — PENDING  / TIMEOUT
    """
    # Считаем MD5-хэш от номера заказа, переводим в число и берем остаток от деления на 10
    h = int(hashlib.md5(str(order_id).encode()).hexdigest(), 16) % 10
    if h <= 6:
        return "SUCCESS", None                     # 70% — успех
    if h == 7:
        return "DECLINED", "INSUFFICIENT_FUNDS"    # 10% — недостаточно средств
    if h == 8:
        return "DECLINED", "CARD_DECLINED"         # 10% — карта отклонена
    return "PENDING", "TIMEOUT"                    # 10% — таймаут (статус "В обработке")

def append_result(payload, payment_id, status, error_code):
    """Сохраняет результат платежа в файл payments_out.csv (добавляет в конец файла)."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    # Формируем строку для CSV-файла
    row = {
        "payment_id": payment_id,
        "order_id": payload["order_id"],
        "recipient": payload["recipient"],
        "purpose": payload["purpose"],
        "amount": f'{float(payload["amount"]):.2f}',  # Оставляем ровно 2 знака после точки (2500 -> 2500.00)
        "currency": payload["currency"],
        "status": status,
        "error_code": error_code or "",     # Если None, пишем пустую строку
        "idempotency_key": payload.get("idempotency_key", ""),
        "created_at": now,
        "confirmed_at": now if status == "SUCCESS" else "",   # Время подтверждения только для успешных
        "correlation_id": "corr_" + payment_id[-4:],          # ID для логов
    }
    # Проверяем, существует ли уже файл (чтобы понять, нужен ли заголовок)
    file_exists = os.path.exists(OUT_CSV)
    # Открываем файл в режиме "a" (append — дописать в конец)
    with open(OUT_CSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()    # Если файла не было, пишем названия колонок
        writer.writerow(row)        # Записываем данные платежа

def main():
    """ Главная функция. Запускает логику скрипта. """
    # Проверяем, передал ли пользователь аргумент (путь к JSON-файлу)
    if len(sys.argv) < 2:
        print("Использование: python 05_app.py payment.json")
        sys.exit(1)

    # 1) читаем входной JSON
    with open(sys.argv[1], encoding="utf-8") as f:
        payload = json.load(f)

    # 2) Загружаем контекст (списки клиник и старые платежи)
    active = load_active_recipients()
    existing_orders, seen_idem = load_existing_payments(OUT_CSV)

    # 3) валидация V-1…V-9
    errors = validate(payload, active, existing_orders, seen_idem)

    # 4) Обработка правила V-9 (Повторный запрос)
    # Если это повтор, мы не выдаем ошибку, а возвращаем старый успешный ответ
    if any(code == "DUPLICATE_REQUEST" for _, code in errors):
        saved = seen_idem[payload["idempotency_key"]]
        print(json.dumps({
            "payment_id": saved["payment_id"],
            "status": saved["status"],
            "error_code": saved["error_code"] or None,
            "idempotent_replay": True,      # Специальный флаг, что это повтор
        }, ensure_ascii=False, indent=2))
        sys.exit(0)

    # 5) Обработка остальных ошибок валидации (V-1...V-8)
    if errors:
        print(json.dumps({
            "status": "ERROR",
            "error_code": "VALIDATION_ERROR",
            "errors": [{"field": f, "code": c} for f, c in errors],
        }, ensure_ascii=False, indent=2))
        sys.exit(2)     # Код 2 = ошибка валидации

    # 6) Если ошибок нет — эмулируем платеж
    status, error_code = emulate_gateway(payload["order_id"])

    # 7) payment_id: pay_demo_ + последние 4 символа order_id
    payment_id = "pay_demo_" + str(payload["order_id"])[-4:]

    # 8) Записываем результат в payments_out.csv
    append_result(payload, payment_id, status, error_code)

    # 9) вывод результата
    print(json.dumps({
        "payment_id": payment_id,
        "status": status,
        "error_code": error_code,
    }, ensure_ascii=False, indent=2))

    # 10) Завершаем программу с правильным exit-кодом
    if status == "SUCCESS":
        sys.exit(0)     # 0 = Успех
    if status == "PENDING":
        sys.exit(3)     # 3 = Таймаут (в обработке)
    sys.exit(1)         # 1 = Отказ шлюза (DECLINED)

if __name__ == "__main__":
    main()