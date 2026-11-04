with open('PHASE0_ARCHITECTURE.md', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('## 10. Next Steps')
if idx >= 0:
    content = content[:idx] + '''## 10. Status

All phases 0-8 have been completed. The implementation includes the full execution engine, failure injection, retry/recovery, idempotency, crash recovery, demo application, dashboard, and tests.
'''
    with open('PHASE0_ARCHITECTURE.md', 'w', encoding='utf-8') as f:
        f.write(content)
    print('done')
else:
    print('not found')
