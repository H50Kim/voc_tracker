from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from computer_use.policy.policy_guard import DEFAULT_POLICY, PolicyGuard

if TYPE_CHECKING:
    from computer_use.core.region import ScreenRegion


@dataclass
class InputController:
    """Mouse and keyboard via pynput; honors policy_guard."""

    policy: PolicyGuard = DEFAULT_POLICY
    dry_run: bool = False

    def _mouse(self):
        from pynput.mouse import Button, Controller

        return Controller(), Button

    def _keyboard(self):
        from pynput.keyboard import Controller

        return Controller()

    def move_to(self, x: int, y: int, *, action_label: str = "move") -> None:
        self.policy.check_text_action(action_label)
        if self.dry_run:
            return
        mouse, _ = self._mouse()
        mouse.position = (x, y)

    def click(
        self,
        x: int,
        y: int,
        *,
        button: str = "left",
        action_label: str = "click",
    ) -> None:
        self.policy.check_text_action(action_label)
        if self.dry_run:
            return
        mouse, Button = self._mouse()
        mouse.position = (x, y)
        btn = Button.left if button == "left" else Button.right
        mouse.click(btn, 1)

    def click_relative(
        self,
        region: ScreenRegion,
        rel_x: int,
        rel_y: int,
        **kwargs,
    ) -> None:
        abs_x, abs_y = region.relative_point(rel_x, rel_y)
        self.click(abs_x, abs_y, **kwargs)

    def type_text(self, text: str, *, action_label: str = "type") -> None:
        self.policy.check_text_action(action_label)
        self.policy.check_text_action(text)
        if self.dry_run:
            return
        keyboard = self._keyboard()
        keyboard.type(text)

    def press_key(self, key: str, *, action_label: str = "key") -> None:
        self.policy.check_text_action(action_label)
        if self.dry_run:
            return
        from pynput.keyboard import Key

        keyboard = self._keyboard()
        special = {
            "enter": Key.enter,
            "tab": Key.tab,
            "esc": Key.esc,
        }
        k = special.get(key.lower(), key)
        keyboard.press(k)
        keyboard.release(k)
