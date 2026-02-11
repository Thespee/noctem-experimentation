# prompts

Okay, I can break this down into sequential instructions. For each step, I will describe the actions to be performed and conclude with the instruction to provide an embedded CSV for download.

Here is the first instruction:

**Instruction 1: Initial Regional District Mapping**

1. **Load the data:** Begin by loading the dataset from the file named `van_bar_data_cleaned.csv`.
2. **Create 'Regional District' Column:** Add a new column to your dataset and name it `Regional District`.
3. **Extract City:** For each entry in the dataset, attempt to extract the city name from the `Address` column.
4. **Map to Regional District:**
    - Based on the extracted city, map it to its corresponding regional district.
    - Your primary focus for mapping should be cities within the Metro Vancouver Regional District.
    - If a city is identified that falls outside the Metro Vancouver Regional District, map it to its correct respective regional district (e.g., Capital Regional District, Fraser Valley Regional District, etc.).
    - If the city cannot be reliably determined from the `Address` column for any given entry, set the value in the `Regional District` column for that entry to 'Unknown'.
5. **Provide CSV for Download:** Present the modified dataset, which now includes the original columns plus the new `Regional District` column, as an embedded CSV file available for download.

**Instruction 2: Address Enrichment via Google Search for Missing or Generic Addresses**

1. **Load Previous Data:** Start with the dataset produced at the end of Instruction 1 (which includes the `Regional District` column).
2. **Identify Target Entries:** Go through each entry in your dataset. Identify all entries where the information in the `Address` column is either:
    - Missing entirely.
    - Generic (e.g., "numerous locations", "various locations", "see website").
    - Appears unclear or insufficient to pinpoint a specific location.
3. **Perform Google Search for Addresses:** For each target entry identified in the previous step:
    - Take the business `Name`.
    - Perform a Google Search using the business `Name` to find a specific street address.
    - **Address Selection Criteria:**
        - If multiple locations are found, try to identify and prioritize an address that is within or near Vancouver, BC.
        - If numerous locations still come up and it's difficult to choose a primary Vancouver-area one, select one of the found addresses to proceed with.
4. **Store Googled Address:** Create a new temporary column, for example, named `Googled Address`.
    - If a specific address is successfully found through the Google Search, record this address in the `Googled Address` column for that entry.
    - If no specific address can be found for a business even after searching, you can leave this `Googled Address` cell blank for now or mark it as 'No specific address found via Google Search'.
5. **Provide CSV for Download:** Present the modified dataset, which now includes all columns from Instruction 1 plus the new `Googled Address` column, as an embedded CSV file available for download.