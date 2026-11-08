
|payment\_id|string|да (сервер)|UUID v4 или `pay\\\_NNNN`|pay\_0001|—|генерируется сервисом, от клиента не приходит|

## Ваша таблица — заполните 11 оставшихся колонок

|Поле|Тип|Обяз.|Ограничение|Пример|Код ошибки|Комментарий|
|-|-|-|-|-|-|-|
|order\_id|string|да|1–64, regex `^[A-Za-z0-9_\-]+$`|ord_1001|INVALID_FORMAT|уникальный идентификатор заказа в системе клиники|
|recipient|string|да|1–64, ID из `recipients.csv`, статус ACTIVE|clinic_medservice|RECIPIENT_NOT_FOUND|ID получателя средств (филиал, врач, партнёр)|
|purpose|string|да|1–200, без PAN (`\d{13,19}`)|Приём терапевта|INVALID_PURPOSE|назначение платежа для истории и чеков|
|amount|number|да|> 0, ≤ 1 000 000, 2 знака после точки|2500.00|AMOUNT_OUT_OF_RANGE / INVALID_AMOUNT_PRECISION|сумма платежа в рублях|
|currency|string|да|enum [RUB]|RUB|UNSUPPORTED_CURRENCY|валюта платежа (ISO 4217)|
|status|string|да (сервер)|CREATED/PENDING/SUCCESS/DECLINED/ERROR/CANCELED|SUCCESS|—|текущее состояние жизненного цикла платежа|
|error\_code|string|нет|из каталога ошибок или пусто|null|—|код причины отказа шлюза или валидации|
|idempotency\_key|string|да|8–64, уникален 24 часа|idem_0001|DUPLICATE_REQUEST|ключ защиты от двойного списания при повторах|
|created\_at|string|да (сервер)|ISO 8601|2025-11-01T08:00:00Z|—|время создания платежа|
|confirmed\_at|string|нет|ISO 8601|null|—|время успешного подтверждения платежа|
|correlation\_id|string|да (сервер)|`corr_NNNN`|corr_0001|—|сквозной ID для трассировки запросов в логах|


