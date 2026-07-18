# fix test_sync_interfaces_raise in test_event_store.py
import os

fp = os.path.join(os.path.dirname(__file__), "test_event_store.py")
with open(fp, "r", encoding="utf-8") as f:
    content = f.read()

OLD = (
    "    def test_sync_interfaces_raise(self):\n"
    "        log, _ = self._make_log()\n"
    "        with pytest.raises(NotImplementedError): _ = log[0]\n"
    "        with pytest.raises(NotImplementedError): list(log)\n"
    '        with pytest.raises(NotImplementedError): log.get_index("x")\n'
    "        with pytest.raises(NotImplementedError): log.get_id(0)\n"
)

NEW = (
    "    def test_sync_getitem_iter_raise(self):\n"
    "        \"\"\"__getitem__ and __iter__ raise NotImplementedError (sync forbidden).\"\"\"\n"
    "        log, _ = self._make_log()\n"
    "        with pytest.raises(NotImplementedError): _ = log[0]\n"
    "        with pytest.raises(NotImplementedError): list(log)\n"
    "\n"
    "    def test_get_index_is_coroutine(self):\n"
    "        \"\"\"get_index is async; sync call returns coroutine, not a plain value.\"\"\"\n"
    "        import inspect\n"
    "        log, _ = self._make_log()\n"
    '        coro = log.get_index("x")\n'
    "        assert inspect.iscoroutine(coro)\n"
    "        coro.close()\n"
    "\n"
    "    def test_get_id_is_coroutine(self):\n"
    "        \"\"\"get_id is async; sync call returns coroutine, not a plain value.\"\"\"\n"
    "        import inspect\n"
    "        log, _ = self._make_log()\n"
    "        coro = log.get_id(0)\n"
    "        assert inspect.iscoroutine(coro)\n"
    "        coro.close()\n"
)

if OLD in content:
    content = content.replace(OLD, NEW)
    with open(fp, "w", encoding="utf-8") as f:
        f.write(content)
    print("patched ok")
else:
    print("NOT FOUND - trying CRLF variant")
    OLD_CRLF = OLD.replace("\n", "\r\n")
    NEW_CRLF = NEW.replace("\n", "\r\n")
    if OLD_CRLF in content:
        content = content.replace(OLD_CRLF, NEW_CRLF)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(content)
        print("patched ok (CRLF)")
    else:
        print("FAILED - cannot locate target block")

