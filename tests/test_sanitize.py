from csv_migrator.sanitize import sanitize_identifier, table_name_from_filename, dedupe_headers


def test_replaces_spaces_and_punctuation_with_underscore():
    assert sanitize_identifier("First Name") == "First_Name"
    assert sanitize_identifier("Order-Date (2024)") == "Order_Date_2024"


def test_collapses_repeated_underscores():
    assert sanitize_identifier("A -- B") == "A_B"


def test_prefixes_leading_digit_with_table():
    assert sanitize_identifier("2024_Sales") == "Table_2024_Sales"


def test_empty_name_becomes_column():
    assert sanitize_identifier("") == "Column"
    assert sanitize_identifier("   ") == "Column"


def test_table_name_from_filename_strips_csv_extension():
    assert table_name_from_filename("Rails to Trails.csv") == "Rails_to_Trails"
    assert table_name_from_filename("2024-data.csv") == "Table_2024_data"


def test_dedupe_headers_appends_suffix_for_duplicates():
    assert dedupe_headers(["Name", "Amount", "Name", "Amount"]) == [
        "Name", "Amount", "Name_1", "Amount_1",
    ]


def test_dedupe_headers_sanitizes_each_name():
    assert dedupe_headers(["First Name", "", "First Name"]) == [
        "First_Name", "Column", "First_Name_1",
    ]


def test_dedupe_headers_avoids_collision_with_generated_suffix():
    result = dedupe_headers(["a", "a", "a_1"])
    lowered = [r.lower() for r in result]
    assert len(lowered) == len(set(lowered))


def test_dedupe_headers_is_case_insensitive():
    result = dedupe_headers(["Name", "name"])
    lowered = [r.lower() for r in result]
    assert len(lowered) == len(set(lowered))
