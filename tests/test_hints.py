# Tests for _hints.py — stampSelector + two-pass dropdown detection
import asyncio
import pytest

# Minimal mock page for evaluate()
class MockPage:
    """Mock Playwright page that evaluates JS via Node.js subprocess."""

    def __init__(self, html: str):
        self.html = html

    async def evaluate(self, js_code):
        """Run EXTRACT_HINTS_JS against self.html using Node.js."""
        import subprocess, json, tempfile, os

        # Wrap the JS: set up DOM from HTML, then run the extraction
        wrapped = """
const {{ JSDOM }} = require('jsdom');
const dom = new JSDOM(`{html}`, {{ pretendToBeVisual: true }});
const document = dom.window.document;
const window = dom.window;

// Polyfill offsetParent (jsdom doesn't support layout)
Object.defineProperty(window.HTMLElement.prototype, 'offsetParent', {{
    get() {{ return this.style.display === 'none' ? null : this.parentElement; }}
}});

// Polyfill CSS.escape
if (!window.CSS) window.CSS = {{}};
if (!window.CSS.escape) {{
    window.CSS.escape = function(s) {{
        return s.replace(/([\\x00-\\x1f\\x7f]|^[0-9]|^-[0-9]|-$|[^\\x80-\\uffff\\w-])/g, function(ch) {{
            return '\\\\' + ch;
        }});
    }};
}}

// Polyfill innerText (jsdom doesn't implement it)
Object.defineProperty(window.HTMLElement.prototype, 'innerText', {{
    get() {{ return this.textContent; }}
}});

// Make document global for the extraction code
global.document = document;
global.CSS = window.CSS;

const fn = {js_fn};
const result = fn();
process.stdout.write(JSON.stringify(result, null, 2));
""".format(
            html=self.html.replace('`', '\\`').replace('${', '\\${'),
            js_fn=js_code,
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(wrapped)
            f.flush()
            try:
                proc = subprocess.run(
                    ['node', f.name],
                    capture_output=True, text=True, timeout=10
                )
                if proc.returncode != 0:
                    raise RuntimeError(f"Node.js error: {proc.stderr}")
                return json.loads(proc.stdout)
            finally:
                os.unlink(f.name)


# =========================================================================
# Test HTML fixtures
# =========================================================================

NATIVE_SELECT_HTML = """
<html><body>
  <label for="country">Country</label>
  <select id="country" name="country">
    <option value="">-- Choose --</option>
    <option value="us">United States</option>
    <option value="tw">Taiwan</option>
    <option value="jp" selected>Japan</option>
  </select>
  <label for="lang">Language</label>
  <select id="lang" name="lang">
    <option value="en" selected>English</option>
    <option value="zh">Chinese</option>
  </select>
</body></html>
"""

ARIA_COMBOBOX_HTML = """
<html><body>
  <div role="combobox" aria-label="Gender" aria-haspopup="listbox"
       aria-controls="gender-list" aria-expanded="true" tabindex="0"
       id="gender">
    <span>Select gender</span>
  </div>
  <ul id="gender-list" role="listbox" aria-label="Gender">
    <li role="option" data-value="2" aria-selected="false">Female</li>
    <li role="option" data-value="1" aria-selected="true">Male</li>
    <li role="option" data-value="3" aria-selected="false">Prefer not to say</li>
    <li role="option" data-value="4" aria-selected="false">Custom</li>
  </ul>
</body></html>
"""

MULTI_DROPDOWN_HTML = """
<html><body>
  <select id="month" name="month" aria-label="Month">
    <option value="">Month</option>
    <option value="1">January</option>
    <option value="2">February</option>
    <option value="3">March</option>
  </select>
  <div role="combobox" aria-label="Gender" aria-haspopup="listbox"
       aria-controls="gender-list" aria-expanded="true" tabindex="0"
       id="gender-trigger">
    <span>Gender</span>
  </div>
  <ul id="gender-list" role="listbox" aria-label="Gender">
    <li role="option" data-value="male">Male</li>
    <li role="option" data-value="female">Female</li>
  </ul>
  <input type="text" id="year" placeholder="Year" />
  <button id="next-btn">Next</button>
  <a href="/help">Help</a>
</body></html>
"""

GOOGLE_MATERIAL_HTML = """
<html><body>
  <div id="gender">
    <div class="VfPpkd-O1htCb">
      <div role="combobox" aria-haspopup="listbox" aria-controls="c12"
           aria-expanded="true" aria-labelledby="c9 c10" tabindex="0">
        <span id="c9">性別</span>
        <span id="c10"></span>
      </div>
      <span id="c12" style="display: none" aria-hidden="true" role="listbox"></span>
      <div class="VfPpkd-xl07Ob">
        <ul role="listbox" aria-label="性別" tabindex="-1">
          <li role="option" data-value="2" aria-selected="false">
            <span>女性</span>
          </li>
          <li role="option" data-value="1" aria-selected="false">
            <span>男性</span>
          </li>
          <li role="option" data-value="3" aria-selected="false">
            <span>不願透露</span>
          </li>
          <li role="option" data-value="4" aria-selected="false">
            <span>自訂</span>
          </li>
        </ul>
      </div>
    </div>
  </div>
</body></html>
"""

HIDDEN_OFFSETPARENT_HTML = """
<html><body>
  <div style="position: fixed; top: 0; left: 0;">
    <div role="combobox" aria-label="Month" aria-haspopup="listbox"
         aria-controls="month-list" tabindex="0" style="position: fixed;">
      <span>1月</span>
    </div>
    <ul id="month-list" role="listbox">
      <li role="option" data-value="1">1月</li>
      <li role="option" data-value="2">2月</li>
      <li role="option" data-value="3">3月</li>
    </ul>
  </div>
</body></html>
"""

DUAL_ROLE_HTML = """
<html><body>
  <div role="combobox" aria-haspopup="listbox" aria-controls="list1"
       aria-label="Color" id="color-combo" tabindex="0">
    <span>Red</span>
  </div>
  <ul id="list1" role="listbox">
    <li role="option" data-value="r">Red</li>
    <li role="option" data-value="g">Green</li>
  </ul>
</body></html>
"""

NO_ID_HTML = """
<html><body>
  <select name="color">
    <option value="r">Red</option>
    <option value="g">Green</option>
  </select>
  <div role="combobox" aria-label="Size" aria-haspopup="listbox"
       aria-controls="size-list" tabindex="0">
    <span>Small</span>
  </div>
  <ul id="size-list" role="listbox">
    <li role="option" data-value="s">Small</li>
    <li role="option" data-value="m">Medium</li>
    <li role="option" data-value="l">Large</li>
  </ul>
</body></html>
"""


# =========================================================================
# Helper
# =========================================================================

def get_js():
    """Load EXTRACT_HINTS_JS from _hints.py"""
    import importlib, sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
    from core.modules.atomic.browser._hints import EXTRACT_HINTS_JS
    return EXTRACT_HINTS_JS


@pytest.fixture
def js_code():
    return get_js()


def run(html, js_code):
    page = MockPage(html)
    return asyncio.get_event_loop().run_until_complete(page.evaluate(js_code))


# =========================================================================
# Tests
# =========================================================================

class TestStampSelector:
    """stampSelector() produces usable selectors"""

    def test_native_select_uses_id(self, js_code):
        result = run(NATIVE_SELECT_HTML, js_code)
        selects = result.get('selects', [])
        assert len(selects) == 2
        assert selects[0]['selector'] == '#country'
        assert selects[1]['selector'] == '#lang'

    def test_no_id_uses_name(self, js_code):
        result = run(NO_ID_HTML, js_code)
        selects = result.get('selects', [])
        # Native select with name="color" but no id
        native = [s for s in selects if s['kind'] == 'native']
        assert len(native) == 1
        assert 'name="color"' in native[0]['selector']

    def test_fallback_uses_data_flyto_hint(self, js_code):
        result = run(NO_ID_HTML, js_code)
        selects = result.get('selects', [])
        custom = [s for s in selects if s['kind'] == 'custom']
        assert len(custom) >= 1
        # The combobox has no id (aria-controls points to size-list, but combobox itself has no id)
        sel = custom[0]['selector']
        assert 'data-flyto-hint' in sel or sel.startswith('#')


class TestTwoPassDetection:
    """Two-pass detection finds triggers correctly"""

    def test_native_select_detected(self, js_code):
        result = run(NATIVE_SELECT_HTML, js_code)
        selects = result.get('selects', [])
        assert all(s['kind'] == 'native' for s in selects)
        assert len(selects) == 2

    def test_aria_combobox_detected(self, js_code):
        result = run(ARIA_COMBOBOX_HTML, js_code)
        selects = result.get('selects', [])
        custom = [s for s in selects if s['kind'] == 'custom']
        assert len(custom) >= 1

    def test_mixed_native_and_custom(self, js_code):
        result = run(MULTI_DROPDOWN_HTML, js_code)
        selects = result.get('selects', [])
        native = [s for s in selects if s['kind'] == 'native']
        custom = [s for s in selects if s['kind'] == 'custom']
        assert len(native) == 1  # month
        assert len(custom) >= 1  # gender


class TestOptionEnumeration:
    """Options are correctly extracted per dropdown"""

    def test_native_options(self, js_code):
        result = run(NATIVE_SELECT_HTML, js_code)
        country = result['selects'][0]
        assert len(country['options']) == 4
        values = [o['value'] for o in country['options']]
        assert 'us' in values
        assert 'tw' in values

    def test_native_selected_state(self, js_code):
        result = run(NATIVE_SELECT_HTML, js_code)
        country = result['selects'][0]
        selected = [o for o in country['options'] if o['selected']]
        assert len(selected) == 1
        assert selected[0]['value'] == 'jp'

    def test_custom_options_with_data_value(self, js_code):
        result = run(ARIA_COMBOBOX_HTML, js_code)
        selects = result.get('selects', [])
        custom = [s for s in selects if s['kind'] == 'custom']
        assert len(custom) >= 1
        gender = custom[0]
        assert len(gender['options']) == 4
        values = [o['value'] for o in gender['options']]
        assert '2' in values  # Female
        assert '1' in values  # Male

    def test_option_selector_present(self, js_code):
        result = run(ARIA_COMBOBOX_HTML, js_code)
        custom = [s for s in result['selects'] if s['kind'] == 'custom']
        for opt in custom[0]['options']:
            assert 'option_selector' in opt
            assert opt['option_selector']  # not empty

    def test_no_over_matching(self, js_code):
        """Multiple dropdowns don't bleed into each other"""
        result = run(MULTI_DROPDOWN_HTML, js_code)
        selects = result['selects']
        for s in selects:
            if s.get('name') and 'Month' in s['name']:
                # month has 4 options (incl. placeholder)
                assert len(s['options']) <= 4
            elif 'Gender' in (s.get('name') or ''):
                assert len(s['options']) == 2


class TestNameResolution:
    """Dropdown names are resolved from ARIA attributes"""

    def test_aria_label(self, js_code):
        result = run(ARIA_COMBOBOX_HTML, js_code)
        custom = [s for s in result['selects'] if s['kind'] == 'custom']
        assert custom[0]['name'] == 'Gender'

    def test_native_select_aria_label(self, js_code):
        result = run(MULTI_DROPDOWN_HTML, js_code)
        native = [s for s in result['selects'] if s['kind'] == 'native']
        assert native[0]['name'] == 'Month'


class TestOtherElements:
    """Inputs, buttons, links still work with stampSelector"""

    def test_inputs_detected(self, js_code):
        result = run(MULTI_DROPDOWN_HTML, js_code)
        inputs = result.get('inputs', [])
        assert len(inputs) >= 1
        assert inputs[0]['selector'] == '#year'
        assert inputs[0]['placeholder'] == 'Year'

    def test_buttons_detected(self, js_code):
        result = run(MULTI_DROPDOWN_HTML, js_code)
        buttons = result.get('buttons', [])
        assert len(buttons) >= 1
        assert any('next' in b.get('id', '').lower() or 'Next' in b.get('text', '') for b in buttons)

    def test_links_detected(self, js_code):
        result = run(MULTI_DROPDOWN_HTML, js_code)
        links = result.get('links', [])
        assert len(links) >= 1
        assert links[0]['text'] == 'Help'

    def test_text_extracted(self, js_code):
        result = run(MULTI_DROPDOWN_HTML, js_code)
        assert 'text' in result
        assert len(result['text']) > 0


class TestSelectOutput:
    """Select output includes kind and current_value"""

    def test_kind_field(self, js_code):
        result = run(MULTI_DROPDOWN_HTML, js_code)
        for s in result['selects']:
            assert 'kind' in s
            assert s['kind'] in ('native', 'custom')

    def test_current_value_field(self, js_code):
        result = run(MULTI_DROPDOWN_HTML, js_code)
        for s in result['selects']:
            assert 'current_value' in s


class TestGoogleMaterial:
    """Google Material Design dropdowns (aria-controls points to empty span)"""

    def test_google_gender_detected(self, js_code):
        result = run(GOOGLE_MATERIAL_HTML, js_code)
        selects = result.get('selects', [])
        assert len(selects) >= 1
        # Should detect as custom
        assert selects[0]['kind'] == 'custom'

    def test_google_gender_options_not_lazy(self, js_code):
        """Options should be found despite aria-controls pointing to empty span"""
        result = run(GOOGLE_MATERIAL_HTML, js_code)
        selects = result.get('selects', [])
        gender = selects[0]
        assert not gender.get('lazy', False), "Should not be lazy — options exist in sibling listbox"
        assert len(gender['options']) == 4

    def test_google_gender_option_values(self, js_code):
        result = run(GOOGLE_MATERIAL_HTML, js_code)
        gender = result['selects'][0]
        values = [o['value'] for o in gender['options']]
        assert '2' in values  # 女性
        assert '1' in values  # 男性
        assert '3' in values  # 不願透露
        assert '4' in values  # 自訂

    def test_google_gender_name_resolved(self, js_code):
        """Name should be resolved from aria-labelledby"""
        result = run(GOOGLE_MATERIAL_HTML, js_code)
        gender = result['selects'][0]
        assert '性別' in gender['name']


class TestNoDuplicates:
    """Elements with both role=combobox and aria-haspopup should not be duplicated"""

    def test_dual_role_no_duplicates(self, js_code):
        """Combobox with aria-haspopup should appear only once"""
        result = run(DUAL_ROLE_HTML, js_code)
        selects = result.get('selects', [])
        assert len(selects) == 1, f"Expected 1, got {len(selects)}: {[s['selector'] for s in selects]}"

    def test_dual_role_has_options(self, js_code):
        result = run(DUAL_ROLE_HTML, js_code)
        assert len(result['selects'][0]['options']) == 2


class TestHiddenOffsetParent:
    """ARIA combobox inside position:fixed (offsetParent=null) should still be detected"""

    def test_fixed_position_combobox_detected(self, js_code):
        result = run(HIDDEN_OFFSETPARENT_HTML, js_code)
        selects = result.get('selects', [])
        assert len(selects) >= 1, "Combobox inside position:fixed should be detected"
        assert selects[0]['kind'] == 'custom'
        assert len(selects[0]['options']) == 3


# =========================================================================
# Real-world framework patterns audit
# =========================================================================

# Ant Design / Headless UI: combobox trigger without aria-controls,
# options rendered as portal outside trigger container
ANT_DESIGN_HTML = """
<html><body>
  <div id="app">
    <div role="combobox" aria-label="Province" aria-expanded="true" tabindex="0">
      <span>Select province</span>
    </div>
  </div>
  <!-- Portal: options rendered outside the combobox container -->
  <div id="ant-select-portal" style="position: absolute; top: 100px;">
    <div role="listbox" aria-label="Province">
      <div role="option" data-value="taipei">Taipei</div>
      <div role="option" data-value="taichung">Taichung</div>
    </div>
  </div>
</body></html>
"""

# Shopify Polaris / Bootstrap: native <select> hidden by CSS,
# visual dropdown is pure div/ul without ARIA roles
BOOTSTRAP_CUSTOM_HTML = """
<html><body>
  <select id="size-native" name="size" style="display: none;">
    <option value="s">Small</option>
    <option value="m">Medium</option>
    <option value="l">Large</option>
  </select>
  <div class="custom-select" tabindex="0">
    <div class="selected-value">Small</div>
    <ul class="dropdown-menu">
      <li data-value="s">Small</li>
      <li data-value="m">Medium</li>
      <li data-value="l">Large</li>
    </ul>
  </div>
</body></html>
"""

# Radix / shadcn: trigger uses aria-haspopup="menu" + role="menubar" pattern
RADIX_MENU_HTML = """
<html><body>
  <button role="combobox" aria-haspopup="listbox" aria-expanded="false"
          aria-controls="radix-list" id="radix-trigger">
    Select fruit...
  </button>
  <div id="radix-list" role="listbox" style="display: none;">
    <div role="option" data-value="apple">Apple</div>
    <div role="option" data-value="banana">Banana</div>
    <div role="option" data-value="cherry" aria-selected="true">Cherry</div>
  </div>
</body></html>
"""

# Multiple native <select> on same page (e-commerce filter)
ECOMMERCE_FILTERS_HTML = """
<html><body>
  <label for="brand">Brand</label>
  <select id="brand" name="brand">
    <option value="">All</option>
    <option value="nike">Nike</option>
    <option value="adidas">Adidas</option>
  </select>
  <label for="size">Size</label>
  <select id="size" name="size">
    <option value="">All</option>
    <option value="s">S</option>
    <option value="m" selected>M</option>
    <option value="l">L</option>
  </select>
  <label for="color">Color</label>
  <select id="color" name="color">
    <option value="">All</option>
    <option value="red">Red</option>
    <option value="blue">Blue</option>
  </select>
</body></html>
"""

# Combobox with aria-owns instead of aria-controls
ARIA_OWNS_HTML = """
<html><body>
  <input type="text" role="combobox" aria-label="Search city"
         aria-owns="city-results" aria-expanded="true" id="city-input">
  <ul id="city-results" role="listbox">
    <li role="option" data-value="nyc">New York</li>
    <li role="option" data-value="la">Los Angeles</li>
    <li role="option" data-value="sf">San Francisco</li>
  </ul>
</body></html>
"""

# Menu-based dropdown: uses role="menu" + role="menuitem" (common in action menus)
MENU_DROPDOWN_HTML = """
<html><body>
  <button aria-haspopup="menu" aria-expanded="true"
          aria-controls="action-menu" id="action-trigger">
    Actions
  </button>
  <div id="action-menu" role="menu">
    <div role="menuitem" data-value="edit">Edit</div>
    <div role="menuitem" data-value="duplicate">Duplicate</div>
    <div role="menuitem" data-value="delete">Delete</div>
  </div>
</body></html>
"""

# Deep nesting: combobox is deeply nested, options container is a sibling far up
DEEP_NESTING_HTML = """
<html><body>
  <div class="page">
    <div class="section">
      <div class="field-group">
        <div class="field-wrapper">
          <div role="combobox" aria-haspopup="listbox" aria-controls="deep-list"
               aria-label="Priority" id="deep-combo">
            Medium
          </div>
        </div>
      </div>
      <ul id="deep-list" role="listbox">
        <li role="option" data-value="low">Low</li>
        <li role="option" data-value="medium" aria-selected="true">Medium</li>
        <li role="option" data-value="high">High</li>
      </ul>
    </div>
  </div>
</body></html>
"""

# Nested: combobox inside a form with other inputs
FORM_WITH_SELECTS_HTML = """
<html><body>
  <form>
    <input type="text" id="name" name="name" placeholder="Name">
    <select id="country" name="country" aria-label="Country">
      <option value="us">United States</option>
      <option value="tw" selected>Taiwan</option>
    </select>
    <div role="combobox" aria-label="City" aria-haspopup="listbox"
         aria-controls="city-list" tabindex="0" id="city-combo">
      <span>Select city</span>
    </div>
    <ul id="city-list" role="listbox">
      <li role="option" data-value="tp">Taipei</li>
      <li role="option" data-value="kh">Kaohsiung</li>
    </ul>
    <input type="email" id="email" name="email" placeholder="Email">
    <button type="submit" id="submit-btn">Submit</button>
  </form>
</body></html>
"""


class TestAntDesignPortal:
    """Ant Design: options in portal outside combobox container"""

    def test_combobox_detected(self, js_code):
        result = run(ANT_DESIGN_HTML, js_code)
        selects = result.get('selects', [])
        assert len(selects) >= 1

    def test_portal_options_lazy(self, js_code):
        """Portal options are OUTSIDE the nearest [id] container,
        so they won't be found — should be lazy, not crash"""
        result = run(ANT_DESIGN_HTML, js_code)
        combo = result['selects'][0]
        # Options are in a portal outside #app, so nearest container search won't find them
        # This is expected: lazy=true, user needs to open dropdown first
        # OR the search walks far enough to find them
        assert combo.get('lazy', False) or len(combo['options']) == 2


class TestBootstrapCustom:
    """Bootstrap: hidden native select + non-ARIA custom dropdown"""

    def test_hidden_native_not_detected(self, js_code):
        """Hidden native select (display:none) should NOT appear"""
        result = run(BOOTSTRAP_CUSTOM_HTML, js_code)
        selects = result.get('selects', [])
        native = [s for s in selects if s['kind'] == 'native']
        assert len(native) == 0, "Hidden native select should be filtered"

    def test_no_aria_custom_not_detected(self, js_code):
        """Pure div/ul without ARIA roles — we do NOT detect these (by design)"""
        result = run(BOOTSTRAP_CUSTOM_HTML, js_code)
        selects = result.get('selects', [])
        # No ARIA roles = no detection. This is intentional.
        assert len(selects) == 0


class TestRadixPattern:
    """Radix/shadcn: button trigger + hidden listbox"""

    def test_trigger_detected(self, js_code):
        result = run(RADIX_MENU_HTML, js_code)
        selects = result.get('selects', [])
        assert len(selects) == 1  # not duplicated despite combobox + haspopup
        assert selects[0]['selector'] == '#radix-trigger'

    def test_options_found(self, js_code):
        result = run(RADIX_MENU_HTML, js_code)
        assert len(result['selects'][0]['options']) == 3

    def test_selected_state(self, js_code):
        result = run(RADIX_MENU_HTML, js_code)
        opts = result['selects'][0]['options']
        selected = [o for o in opts if o['selected']]
        assert len(selected) == 1
        assert selected[0]['value'] == 'cherry'


class TestEcommerceFilters:
    """Multiple native selects (e-commerce filter page)"""

    def test_all_three_detected(self, js_code):
        result = run(ECOMMERCE_FILTERS_HTML, js_code)
        selects = result.get('selects', [])
        assert len(selects) == 3

    def test_correct_selectors(self, js_code):
        result = run(ECOMMERCE_FILTERS_HTML, js_code)
        sels = [s['selector'] for s in result['selects']]
        assert '#brand' in sels
        assert '#size' in sels
        assert '#color' in sels

    def test_options_not_mixed(self, js_code):
        """Each select has its own options, not mixed"""
        result = run(ECOMMERCE_FILTERS_HTML, js_code)
        for s in result['selects']:
            if s['selector'] == '#brand':
                vals = [o['value'] for o in s['options']]
                assert 'nike' in vals
                assert 's' not in vals  # from size, not brand
            elif s['selector'] == '#size':
                vals = [o['value'] for o in s['options']]
                assert 'm' in vals
                assert 'nike' not in vals

    def test_selected_state(self, js_code):
        result = run(ECOMMERCE_FILTERS_HTML, js_code)
        size = [s for s in result['selects'] if s['selector'] == '#size'][0]
        selected = [o for o in size['options'] if o['selected']]
        assert len(selected) == 1
        assert selected[0]['value'] == 'm'


class TestAriaOwns:
    """Combobox using aria-owns instead of aria-controls"""

    def test_detected_via_aria_owns(self, js_code):
        result = run(ARIA_OWNS_HTML, js_code)
        selects = result.get('selects', [])
        assert len(selects) == 1
        assert selects[0]['selector'] == '#city-input'

    def test_options_found(self, js_code):
        result = run(ARIA_OWNS_HTML, js_code)
        assert len(result['selects'][0]['options']) == 3


class TestFormMixed:
    """Form with both native select and ARIA combobox + other inputs"""

    def test_both_selects_detected(self, js_code):
        result = run(FORM_WITH_SELECTS_HTML, js_code)
        selects = result.get('selects', [])
        assert len(selects) == 2
        kinds = {s['kind'] for s in selects}
        assert 'native' in kinds
        assert 'custom' in kinds

    def test_inputs_also_detected(self, js_code):
        result = run(FORM_WITH_SELECTS_HTML, js_code)
        inputs = result.get('inputs', [])
        assert len(inputs) >= 2
        names = [i['name'] for i in inputs]
        assert 'name' in names
        assert 'email' in names

    def test_button_also_detected(self, js_code):
        result = run(FORM_WITH_SELECTS_HTML, js_code)
        buttons = result.get('buttons', [])
        assert len(buttons) >= 1

    def test_native_select_options(self, js_code):
        result = run(FORM_WITH_SELECTS_HTML, js_code)
        native = [s for s in result['selects'] if s['kind'] == 'native'][0]
        assert len(native['options']) == 2
        assert native['name'] == 'Country'

    def test_custom_combobox_options(self, js_code):
        result = run(FORM_WITH_SELECTS_HTML, js_code)
        custom = [s for s in result['selects'] if s['kind'] == 'custom'][0]
        assert len(custom['options']) == 2
        assert custom['name'] == 'City'


class TestMenuDropdown:
    """Menu-based dropdown: aria-haspopup="menu" + role="menuitem" """

    def test_trigger_detected(self, js_code):
        result = run(MENU_DROPDOWN_HTML, js_code)
        selects = result.get('selects', [])
        assert len(selects) == 1
        assert selects[0]['selector'] == '#action-trigger'

    def test_menuitem_options_found(self, js_code):
        """role="menuitem" should be recognized as options"""
        result = run(MENU_DROPDOWN_HTML, js_code)
        opts = result['selects'][0]['options']
        assert len(opts) == 3
        labels = [o['label'] for o in opts]
        assert 'Edit' in labels
        assert 'Duplicate' in labels
        assert 'Delete' in labels

    def test_menuitem_data_values(self, js_code):
        result = run(MENU_DROPDOWN_HTML, js_code)
        opts = result['selects'][0]['options']
        vals = [o['value'] for o in opts]
        assert 'edit' in vals
        assert 'delete' in vals


class TestDeepNesting:
    """Combobox deeply nested, listbox is a sibling several levels up"""

    def test_detected(self, js_code):
        result = run(DEEP_NESTING_HTML, js_code)
        selects = result.get('selects', [])
        assert len(selects) == 1

    def test_options_found_despite_depth(self, js_code):
        """Walk-up search should find listbox within 6 levels"""
        result = run(DEEP_NESTING_HTML, js_code)
        combo = result['selects'][0]
        # aria-controls points to #deep-list, so it should find directly
        assert len(combo['options']) == 3

    def test_name_resolved(self, js_code):
        result = run(DEEP_NESTING_HTML, js_code)
        assert result['selects'][0]['name'] == 'Priority'
