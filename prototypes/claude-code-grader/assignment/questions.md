# CAP3321C Data Wrangling with Python: Final Project (Section A)

> FAKE assignment for the EasyGrade prototype. The dataset and all names are synthetic.

## Dataset

**Miami-Dade Restaurant Inspections 2025 (synthetic)**, file `mdc_restaurant_inspections_2025.csv`

| Column | Description |
|--------|-------------|
| `inspection_id` | Unique ID for each inspection |
| `restaurant_name` | Name of the restaurant |
| `zip_code` | 5-digit ZIP code of the restaurant |
| `inspection_date` | Date of the inspection (2025) |
| `cuisine` | Cuisine category (e.g., Cuban, Haitian, Italian, Seafood) |
| `score` | Inspection score, 0 to 100 |
| `violations` | Number of violations recorded |
| `result` | `Pass`, `Conditional`, or `Fail` |

## Section A Questions

**Q1. Cleaning.** Find and handle missing values, convert columns to the correct data types (`inspection_date` as a date, `score` and `violations` as numbers, `zip_code` as a 5-character string), and remove duplicate inspections. Explain each decision in a Markdown cell and report how many inspections remain after cleaning.

**Q2. Fail rate by ZIP code.** Which ZIP codes have the highest fail rate (share of inspections with `result == "Fail"`)? Show the top 10 in a bar chart.

**Q3. Scores over time.** How does the average inspection score change month by month in 2025? Show a line chart.

**Q4. Violations by cuisine.** Which cuisines have the most violations per inspection? Show a table and write a summary of what you observe.

Every question needs a written summary that explains what the results mean, not only the numbers. All charts need a title, axis labels, and a legend where relevant.

## Submission Rules

1. Work in pairs. Submit **one** Jupyter notebook named `Lastname1_Lastname2_FinalProject.ipynb` (for example `Rivera_Chen_FinalProject.ipynb`).
2. The **first cell** of the notebook must be a Markdown header with exactly these lines:

   ```
   **Students:** First Last, First Last
   **Section:** ...
   **Date:** ...
   **Responsibilities:** ...
   ```

3. Run the notebook top to bottom (Kernel > Restart & Run All) before submitting. Remove leftover or unused cells.
4. Submit a recorded presentation of **at most 5 minutes**. **Both partners must speak.** Focus on what you found and refer to your charts.
5. Graded with the Final Project Rubric (200 points).
