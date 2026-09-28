import sys
sys.path.insert(0, 'web')
sys.path.insert(0, 'scripts')
from starlette.testclient import TestClient
from main import app

client = TestClient(app)
r = client.get('/')
assert r.status_code == 200
html = r.text

assert 'display: none; justify-content: center;' in html, 'display: none missing from .modal-overlay CSS'
assert '.modal-overlay.active' in html, '.modal-overlay.active missing'
assert 'id="batchHoldingModal" class="modal-overlay" style="display:none;"' in html, 'batchHoldingModal not hidden'
assert 'id="holdingModal" class="modal-overlay" style="display:none;"' in html, 'holdingModal not hidden'
assert 'function openModal(id)' in html, 'openModal missing'
assert 'function closeModal(id)' in html, 'closeModal missing'
print('VERIFIED: All modal default hidden & close handlers are in place!')
