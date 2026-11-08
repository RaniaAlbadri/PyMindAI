import unittest

from bot import MAX_HISTORY_MESSAGES, SYSTEM_PROMPT, build_messages


class BuildMessagesTests(unittest.TestCase):
    def test_system_instruction_and_question(self):
        result = build_messages([], "Hello")
        self.assertEqual(result[0], {"role": "system", "content": SYSTEM_PROMPT})
        self.assertEqual(result[-1], {"role": "user", "content": "Hello"})

    def test_only_recent_history_is_sent(self):
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": str(i)}
            for i in range(MAX_HISTORY_MESSAGES + 4)
        ]
        result = build_messages(history, "Next")
        self.assertEqual(len(result), MAX_HISTORY_MESSAGES + 2)
        self.assertEqual(result[1]["content"], "4")
        self.assertEqual(result[-1]["content"], "Next")


if __name__ == "__main__":
    unittest.main()
