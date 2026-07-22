# `utilities/`: The Essential Toolkit and Metadata Magic

Alright, this `utilities/` directory is where we keep all the handy tools and clever bits of code that serve as the backbone for various parts of the `gnss-product-management` package. These aren't tied to any single major component like factories or servers, but they're absolutely essential for keeping everything running smoothly and consistently.

You'll find two main types of functionality here: general-purpose helpers and specialized metadata calculation magic.

### `helpers.py`: The Swiss Army Knife

This file is a collection of fundamental, low-level utility functions that are called upon repeatedly throughout the system. Think of it as our coding "Swiss Army Knife" – always useful, always reliable.

Key functions include:

*   **`hash_file()`**: Essential for data integrity! This computes the SHA-256 hash of any file, crucial for verifying that a downloaded product hasn't been tampered with (used extensively by the `lockfile/` module).
*   **`_ensure_datetime()`**: Standardizes `datetime` objects to be timezone-aware UTC, preventing headaches when dealing with various time formats.
*   **`_listify()`**: A simple yet effective helper to ensure that a variable is always treated as a list, simplifying API interactions.
*   **`expand_dict_combinations()`**: A powerful function that takes a dictionary of lists and generates every possible combination of values, vital for building exhaustive query permutations (used by the `QueryFactory`).
*   **`_PassthroughDict`**: A custom dictionary subclass that helps with string formatting by returning unresolved placeholders instead of raising errors, ensuring our filename template expansion is robust.

### `metadata_funcs.py`: The Time-Traveling Calculator

This file is a bit more specialized, focusing on the clever task of dynamically calculating metadata values based on a given date. This is how we fill in those date-sensitive placeholders in our filename templates without hardcoding anything.

Key functionality:

*   **Date-Derived Functions**: Contains a suite of "pure functions" (e.g., `_ddd` for day-of-year, `_gpsweek` for GPS week number, `_yyyy` for the year, `_refframe` for the correct IGS reference frame based on the epoch). Each takes a `datetime` object and returns the corresponding metadata string.
*   **`register_computed_fields()`**: This is the magic button that wires all these date-derived functions into the `ParameterCatalog`. When our `ProductEnvironment` calls this, it essentially teaches the `ParameterCatalog` how to dynamically compute fields like `GPSWEEK` or `YYYY` whenever a query needs them for a specific date.

In summary, the `utilities/` module might seem like a grab-bag, but it provides foundational reliability (`helpers.py`) and specialized intelligence (`metadata_funcs.py`) that are indispensable for the efficient and accurate operation of our entire GNSS product ETL system. It keeps things consistent, robust, and dynamically aware of the passage of time!
