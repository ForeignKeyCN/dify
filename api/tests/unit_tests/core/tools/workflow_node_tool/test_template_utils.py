from core.tools.workflow_node_tool.template_utils import (
    extract_http_template_parameter_names,
    extract_template_parameter_names,
    render_template_with_parameters,
)


def test_extract_template_parameter_names_supports_hash_and_simple_templates():
    names = extract_template_parameter_names(
        "https://api.example.com/{{#start.query#}}?lang={{language}}"
    )

    assert names == ["start_query", "language"]


def test_extract_http_template_parameter_names_collects_url_and_body_templates():
    node_config = {
        "url": "https://api.example.com/{{endpoint}}",
        "body": {
            "type": "json",
            "data": [
                {
                    "key": "",
                    "type": "text",
                    "value": '{"q":"{{#start.query#}}","locale":"{{locale}}"}',
                }
            ],
        },
    }

    assert extract_http_template_parameter_names(node_config) == [
        "endpoint",
        "start_query",
        "locale",
    ]


def test_render_template_with_parameters_replaces_both_template_styles():
    rendered = render_template_with_parameters(
        "https://api.example.com/{{#start.query#}}?lang={{language}}",
        {
            "start_query": "search",
            "language": "en",
        },
    )

    assert rendered == "https://api.example.com/search?lang=en"
