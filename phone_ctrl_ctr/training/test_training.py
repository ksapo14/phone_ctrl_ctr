import unittest
from collections import Counter
from build_data import build
from functions import parse_output, to_command, validate_call
from train import ROOT, balance_rows, encode_row, load_data


class TrainingTests(unittest.TestCase):
    def test_corpus_and_split_integrity(self):
        rows = load_data(ROOT / "data")
        self.assertEqual(rows, build())
        for split in rows.values():
            for row in split:
                call = row["messages"][-1]["tool_calls"][0]["function"]
                validate_call(**call)
        balanced = balance_rows(rows["train"], 42)
        counts = Counter(r["messages"][-1]["tool_calls"][0]["function"]["name"] for r in balanced)
        self.assertEqual(len(set(counts.values())), 1)
        self.assertEqual(balanced, balance_rows(rows["train"], 42))

    def test_strict_parser_and_adapter(self):
        for split in build().values():
            for row in split:
                expected = row["messages"][-1]["tool_calls"][0]["function"]
                args = ",".join(f"{k}:<escape>{v}<escape>" if isinstance(v, str) else f"{k}:{v}" for k, v in expected["arguments"].items())
                raw = f"<start_function_call>call:{expected['name']}{{{args}}}<end_function_call><start_function_response>"
                self.assertEqual(parse_output(raw), expected)
                self.assertEqual(to_command(**expected), row["expected_command"])
        bad = [
            "Some text <start_function_call>call:list_windows{}<end_function_call>",
            "<start_function_call>call:set_volume{percent:101}<end_function_call>",
            "<start_function_call>call:launch_app{app:<escape>powershell<escape>}<end_function_call>",
            "<start_function_call>call:set_volume{percent:50,percent:60}<end_function_call>",
            "<start_function_call>call:set_volume{percent:50,}<end_function_call>",
            "<start_function_call>call:get<eos>_state{}<end_function_call>",
            "<start_function_call>call:get_state{}<end_function_call>" * 2,
        ]
        for text in bad:
            with self.assertRaises(ValueError): parse_output(text)
        with self.assertRaises(ValueError): validate_call("set_volume", {"percent": True})

    def test_masking_and_no_silent_truncation(self):
        class Tokenizer:
            def apply_chat_template(self, messages, **kwargs):
                return [1, 2, 3] if kwargs["add_generation_prompt"] else [1, 2, 3, 4, 5]
        row = {"id": "example", "messages": [{}, {}, {}]}
        self.assertEqual(encode_row(Tokenizer(), row, 5)["labels"], [-100, -100, -100, 4, 5])
        with self.assertRaises(ValueError): encode_row(Tokenizer(), row, 4)
        class BrokenTokenizer:
            def apply_chat_template(self, messages, **kwargs):
                return [1, 2] if kwargs["add_generation_prompt"] else [3, 4, 5]
        with self.assertRaises(ValueError): encode_row(BrokenTokenizer(), row, 8)


if __name__ == "__main__": unittest.main()
