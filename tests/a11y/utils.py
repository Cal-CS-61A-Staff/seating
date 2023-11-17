AXE_SCRIPT_CONTENT = None
AXE_CONFIG_SCRIPT_CONTENT = None


def load_axe_scripts():
    print("Loading axe scripts...")
    global AXE_SCRIPT_CONTENT, AXE_CONFIG_SCRIPT_CONTENT
    with open('tests/a11y/axe.min.js', 'r') as f:
        AXE_SCRIPT_CONTENT = f.read()
    with open('tests/a11y/axe_config.js', 'r') as f:
        AXE_CONFIG_SCRIPT_CONTENT = f.read()


def run_axe(driver):
    if AXE_SCRIPT_CONTENT is None or AXE_CONFIG_SCRIPT_CONTENT is None:
        load_axe_scripts()

    driver.execute_script(AXE_SCRIPT_CONTENT)
    driver.execute_script(AXE_CONFIG_SCRIPT_CONTENT)
    return driver.execute_script("return axe.run(AXE_CONFIG);")


def print_violations(report):
    violations = report.get('violations', [])
    if len(violations) == 0:
        print("No violations found!")
        return
    for i, violation in enumerate(violations, start=1):
        print(f"Violation {i}:")
        print(f"  ID: {violation['id']}")
        print(f"  Description: {violation['description']}")
        print(f"  Impact: {violation['impact']}")
        for node in violation['nodes']:
            print(f"  - Selector: {node['target']}")
            print(f"    HTML: {node['html']}")
            if len(node['any']) > 0:
                print(f"    Remediation: {node['any'][0]['message']}")


def save_report(title, report):
    from pathlib import Path
    Path("axe").mkdir(parents=True, exist_ok=True)
    with open(f"axe/{title}.json", "w") as f:
        import json
        json.dump(report, f, indent=2)


def assert_no_violations(report, print_if_violations=True):
    if len(report.get('violations', [])) > 0 and print_if_violations:
        print_violations(report)
    assert len(report['violations']) == 0
