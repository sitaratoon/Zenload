from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

class KeyboardBuilder:
    def __init__(self, localization, settings_manager):
        self.localization = localization
        self.settings_manager = settings_manager

    def get_message(self, user_id: int, key: str, **kwargs) -> str:
        """Get localized message"""
        settings = self.settings_manager.get_settings(user_id)
        return self.localization.get(settings.language, key, **kwargs)

    def build_main_keyboard(self, user_id: int) -> ReplyKeyboardMarkup:
        """Build main keyboard with common actions"""
        keyboard = [
            [
                KeyboardButton(self.get_message(user_id, 'btn_settings')),
                KeyboardButton(self.get_message(user_id, 'btn_help')),
                KeyboardButton(self.get_message(user_id, 'btn_donate'))
            ]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def build_settings_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        """Build settings menu keyboard"""
        keyboard = [
            [
                InlineKeyboardButton(self.get_message(user_id, 'btn_language'), callback_data="settings:language"),
                InlineKeyboardButton(self.get_message(user_id, 'btn_quality'), callback_data="settings:quality")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    def build_language_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        """Build language selection keyboard"""
        keyboard = [
            [
                InlineKeyboardButton(self.get_message(user_id, 'btn_russian'), callback_data="set_lang:ru"),
                InlineKeyboardButton(self.get_message(user_id, 'btn_english'), callback_data="set_lang:en")
            ],
            [InlineKeyboardButton(self.get_message(user_id, 'btn_back'), callback_data="settings:back")]
        ]
        return InlineKeyboardMarkup(keyboard)

    def build_quality_keyboard(self, user_id: int) -> InlineKeyboardMarkup:
        """Build quality selection keyboard"""
        keyboard = [
            [InlineKeyboardButton(
                self.get_message(user_id, 'btn_ask'),
                callback_data="set_quality:ask"
            )],
            [InlineKeyboardButton(
                self.get_message(user_id, 'btn_best'),
                callback_data="set_quality:best"
            )],
            [InlineKeyboardButton(self.get_message(user_id, 'btn_back'), callback_data="settings:back")]
        ]
        return InlineKeyboardMarkup(keyboard)

    def build_format_selection_keyboard(self, user_id: int, formats: list) -> InlineKeyboardMarkup:
        """Build format selection keyboard for downloads"""
        keyboard = []
        for fmt in formats:
            keyboard.append([InlineKeyboardButton(
                self.get_message(user_id, 'quality_format', quality=fmt['quality'], ext=fmt['ext']),
                callback_data=f"quality:{fmt['id']}"
            )])
        keyboard.append([InlineKeyboardButton(
            self.get_message(user_id, 'best_quality'),
            callback_data="quality:best"
        )])
        return InlineKeyboardMarkup(keyboard)

