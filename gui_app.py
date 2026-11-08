import streamlit as st
import importlib.util
import uuid
import csv
from datetime import datetime

# Подключаем наш основной файл с логикой
# Мы используем importlib, чтобы подгрузить наш файл 05_app.py как модуль.
# Это позволяет использовать написанные там функции валидации и эмуляции.
spec = importlib.util.spec_from_file_location("app", "05_app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

# Настройка страницы
st.set_page_config(page_title="Оплата услуг - Мед-Сервис", page_icon="🏥", layout="centered")

# --- Стилизация ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { background-color: #28a745; color: white; width: 100%; height: 50px; font-size: 20px; border-radius: 10px; }
    .stButton>button:hover { background-color: #218838; color: white; }
    .receipt { padding: 20px; background-color: white; border-radius: 10px; border: 1px solid #ddd; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-top: 20px; }
    </style>
""", unsafe_allow_html=True)

st.title("🏥 Мед-Сервис")
st.subheader("Оплата медицинских услуг")

# Справочник услуг (взяты реальные названия и цены из payments.csv)
services = {
    "Приём терапевта": {"price": 2500.00, "recipient": "clinic_medservice_therapy", "display": "Терапевтическое отделение"},
    "УЗИ": {"price": 1800.00, "recipient": "clinic_medservice_uzi", "display": "Кабинет УЗИ"},
    "Анализ крови": {"price": 1800.00, "recipient": "clinic_medservice_lab_blood", "display": "Лаборатория анализов крови"},
    "Приём кардиолога": {"price": 3000.00, "recipient": "clinic_medservice_cardio", "display": "Кардиологическое отделение"},
    "МРТ": {"price": 12000.00, "recipient": "clinic_medservice_mri", "display": "Кабинет МРТ"},
    "Приём педиатра": {"price": 2200.00, "recipient": "clinic_medservice_pediatrics", "display": "Педиатрическое отделение"},
    "Физиотерапия": {"price": 1500.00, "recipient": "clinic_medservice_physio", "display": "Физиотерапевтическое отделение"},
    "Анализ мочи": {"price": 900.00, "recipient": "clinic_medservice_lab_urine", "display": "Лаборатория анализов мочи"},
    "Приём хирурга": {"price": 2700.00, "recipient": "clinic_medservice_surgery", "display": "Хирургическое отделение"},
    "Рентген": {"price": 3200.00, "recipient": "clinic_medservice_xray", "display": "Рентген-кабинет"}
}

# Генерируем скрытые технические данные (клиент их не видит)
# Session_state сохраняет значения при перезагрузке страницы
if "order_id" not in st.session_state:
    # Генерируем случайный номер заказа
    st.session_state.order_id = "ord_" + uuid.uuid4().hex[:6]
if "idem_key" not in st.session_state:
    # Ключ защиты от двойного списания
    st.session_state.idem_key = "idem_" + uuid.uuid4().hex[:8]

# --- 3. Интерфейс для пациента ---
st.markdown("### Выберите услугу")

# Две колонки: слева выбор, справа цена
col1, col2 = st.columns([2, 1])
with col1:
    purpose = st.selectbox("Что вы хотите оплатить?", list(services.keys()), label_visibility="collapsed")
    # Получаем данные выбранной услуги
selected_service = services[purpose]
amount = selected_service["price"]
recipient = selected_service["recipient"]
with col2:
    # Показываем цену, но её нельзя изменить руками
    st.markdown(f"<h3 style='text-align: right; color: #28a745;'>{amount:.2f} ₽</h3>", unsafe_allow_html=True)
# Показываем пациенту, куда уйдет платеж
st.info(f"📍 Платёж будет направлен в: **{selected_service['display']}**")
st.write("---")

# Технические данные
currency = "RUB"

# Кнопка оплаты
if st.button("Оплатить"):
    # Собираем данные для отправки в нашу логику
    payload = {
        "order_id": st.session_state.order_id,
        "recipient": recipient, 
        "purpose": purpose,
        "amount": str(amount),
        "currency": currency,
        "idempotency_key": st.session_state.idem_key
    }
    
    # Вызываем валидацию (проверка правил V-1...V-9)
    active_recipients = app.load_active_recipients()
    existing_orders, seen_idem = app.load_existing_payments(app.OUT_CSV)
    errors = app.validate(payload, active_recipients, existing_orders, seen_idem)
    
    if errors:
        # Выводим причину ошибки
        st.error("❌ Ошибка валидации данных:")
        for field, code in errors:
            st.warning(f"Поле **{field}**: `{code}`")
    else:
         # Эмуляция платежного шлюза
        status, error_code = app.emulate_gateway(payload["order_id"])
        
        # Запись результата в базу (CSV)
        payment_id = "pay_demo_" + str(payload["order_id"])[-4:]
        try:
            app.append_result(payload, payment_id, status, error_code)
        except PermissionError:
            st.error("❌ Ошибка: Файл базы данных (payments_out.csv) открыт в другой программе. Пожалуйста, закройте Excel и попробуйте снова.")
            st.stop()   # Останавливаем программу, чтобы не показывать пустой чек
        
        # Красивый вывод результата (Чек)
        st.markdown("<div class='receipt'>", unsafe_allow_html=True)
        
        if status == "SUCCESS":
            st.success("✅ Платёж успешно проведен!")
            st.markdown(f"**Услуга:** {purpose}")
            st.markdown(f"**Сумма:** {amount:.2f} ₽")
            st.markdown(f"**Номер транзакции:** {payment_id}")
            st.markdown(f"**Дата:** {datetime.now().strftime('%d.%m.%Y %H:%M')}")
            st.info("Ждём вас в клинике! Пожалуйста, покажите этот экран на ресепшене.")
            
        elif status == "PENDING":
            st.warning("⏳ Платёж обрабатывается банком...")
            st.markdown("Банк не ответил вовремя. Деньги не списаны. Пожалуйста, подождите или обновите страницу через минуту.")
            
        else: # DECLINED
            st.error("❌ Платёж отклонен банком.")
            if error_code == "INSUFFICIENT_FUNDS":
                st.markdown("Причина: **Недостаточно средств на карте**.")
            elif error_code == "CARD_DECLINED":
                st.markdown("Причина: **Банк отклонил операцию**. Попробуйте другую карту.")
            else:
                st.markdown(f"Код ошибки: {error_code}")
                
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Кнопка сброса для нового заказа
        st.write("---")
        if st.button("Вернуться на главную (Новый заказ)"):
            del st.session_state.order_id
            del st.session_state.idem_key
            st.rerun()