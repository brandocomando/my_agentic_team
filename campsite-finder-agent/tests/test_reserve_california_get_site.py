from datetime import date
import json
import shutil
import subprocess
from unittest.mock import Mock, call

import pytest

from campsite_finder_agent import reserve_california as rc


@pytest.fixture
def watch(monkeypatch):
    page = Mock(url='https://www.reservecalifornia.com/park/709/666')
    browser = Mock()
    playwright = Mock()
    playwright.chromium.connect_over_cdp.return_value = browser
    context = Mock()
    context.__enter__ = Mock(return_value=playwright)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(rc, 'require_playwright', lambda: lambda: context)
    monkeypatch.setattr(rc, '_find_reserve_california_page', lambda _: page)
    setter = Mock(return_value='set')
    monkeypatch.setattr(rc, 'set_reserve_california_search_dates', setter)
    page.evaluate.side_effect = [
        {'action': 'waiting-for-availability', 'bookNowClicked': False},
        {'action': 'details-filled', 'bookNowClicked': True},
    ]
    events = Mock()
    events.attach_mock(page.reload, 'reload')
    events.attach_mock(setter, 'set_dates')
    events.attach_mock(page.evaluate, 'evaluate')
    rc.get_reserve_california_site(
        'http://localhost:9222', page.url, '76', date(2027, 3, 20), 2,
        refresh_window_start='00:00:00', refresh_window_end='23:59:59',
        max_run_seconds=10,
    )
    return page, setter, events


def test_search_previous_day_but_book_actual_arrival(watch):
    page, setter, events = watch
    assert setter.call_args_list == [call(page, date(2027, 3, 19), 1)] * 3
    assert page.reload.call_count == 2
    assert [event[0] for event in events.mock_calls] == [
        'set_dates', 'reload', 'set_dates', 'evaluate',
        'reload', 'set_dates', 'evaluate',
    ]
    page.wait_for_timeout.assert_called_once_with(1000)
    args = page.evaluate.call_args.args[1]
    assert args['startDate'] == '2027-03-20'
    assert args['nights'] == 2


@pytest.mark.parametrize('available', [True, False])
def test_site_click_selects_requested_duration_before_booking(watch, available):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required to exercise browser JavaScript')
    page, _, _ = watch
    script, args = page.evaluate.call_args.args
    args = {**args, 'clickBookNow': True}
    harness = '''
const events = [];
global.setTimeout = (fn) => { fn(); return 0; };
global.Event = class { constructor(type) { this.type = type; } };
const duration = {value:'1', disabled:false, options:OPTIONS,
 dispatchEvent(e) { events.push(e.type + ':' + this.value); }};
const cell = {className:'available', href:'',
 getAttribute(name) { return name === 'aria-label' ? 'Campsite #76 03/20/2027' : ''; },
 scrollIntoView(){}, click(){events.push('site');}};
const button = {disabled:false,hasAttribute(){return false;},getAttribute(){return null;},
 scrollIntoView(){},click(){events.push('book:' + duration.value);}};
global.document = {
 querySelectorAll(selector) { return selector.startsWith('a.unit-slice') ? [cell] : []; },
 querySelector(selector) {
  if (selector === '#nights-select') return duration;
  if (selector === '#checkout-button') return button;
  return null;
 }
};
(async () => {const result = await (SCRIPT)(ARGS); console.log(JSON.stringify({result,events}));})();
'''
    options = [{'value': '1', 'disabled': False}, {'value': '2', 'disabled': not available}]
    harness = harness.replace('OPTIONS', json.dumps(options)).replace('SCRIPT', script).replace('ARGS', json.dumps(args))
    result = subprocess.run([node, '-e', harness], capture_output=True, text=True, check=True)
    output = json.loads(result.stdout)
    if available:
        assert output['events'][:4] == ['site', 'input:2', 'change:2', 'book:2']
        # Missing pre-cart details must still prevent reserving the unit.
        assert output['result']['action'] == 'details-validation-failed'
    else:
        assert output['events'] == ['site']
        assert output['result']['action'] == 'requested-nights-unavailable'
        assert not output['result']['bookNowClicked']
