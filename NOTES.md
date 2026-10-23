# NOTES

_Fill this in as you work. It matters as much as the code._

## Part 1: Diagnosis of the eval failures

- Case 1 (overdue Sysco): The model returned the right vendor and status filters, but the query runner searched every customer's invoices. It included an overdue Sysco invoice belonging to customer 2210. The service should have limited the data to customer 1049 before applying the requested filters.
- Case 2 (total owed): The model returned a valid query inside a Markdown code block, with extra text before and after it. The service tried to parse the whole response as JSON, so parsing failed and the request raised an exception instead of returning an answer.
- Case 3 (who do I owe most): The model used `vendor_name`, but the schema calls that column `vendor`. It also asked to group invoices by vendor, which the query runner does not support. The runner did not validate either issue and ignored the grouping request, so it returned invoices across all customers instead of the requested vendor answer.
- Case 4 (biggest invoice): The model added a filter for customer 2210 even though customer 1049 asked the question. The query runner trusted that filter and searched the other customer's invoices. Tenant scope must come from the service, not from the model's query.
- Case 5 (how many open): The model response was incomplete and not valid JSON. The service tried to parse it directly, and the parsing error escaped as an exception. Bad model output should be handled as a normal no-answer case.
- Case 6 (is this a good deal): The model indicated that it could not answer, but the service did not recognize that response as a no-answer. It ran an empty query instead, which returned invoices from every customer. The service needs to preserve the model's no-answer signal and return a clear, safe response.

## Judgement calls

- `How I handle a hallucinated column, and why`: Before running a query, I check every column used in filters, aggregates, sorting, and grouping against the invoice schema. An unknown name such as `vendor_name` produces a no-answer. I do not guess that it means `vendor`; choosing the wrong interpretation could return a plausible but incorrect answer. Grouping is also rejected because the runner does not implement it. Case 3 in the supplied eval expects `Aramark` despite requesting the unknown `vendor_name` column and grouping. I am leaving that fixture unchanged as requested, so that case will report a mismatch even though the service correctly declines the invalid spec.
- `Where I enforce tenant scope, and why there`: The prompt contains the schema, but neither customer IDs nor invoice rows. The query runner starts with only invoices for the requesting customer; this is the actual security boundary, since the model can ignore prompt instructions or return a customer filter of its own. Keeping tenant identifiers and records out of the prompt minimizes data disclosed to the model. Model-provided `customer_id` filters are ignored; the caller's customer ID is authoritative.
- `What "no-answer" looks like, and when I return it`: The response uses `answer_kind: "no_answer"` and a short reason. This is distinct from a valid query with zero matching rows. It is returned for malformed or missing JSON, a response with no query, and the model's explicit `answer: null` response.

## What I'd do next with more time

- Verify the customer's identity at the service boundary and derive `customer_id` from the authenticated user, rather than trusting a caller supplied ID. The query runner enforces tenant filtering but the service still needs to ensure a user cannot ask on behalf of another customer.
- Validate filter values against the schema types and allowed values, such as requiring a numeric amount and a known invoice status. This would reject malformed specs before they reach the query runner.
- Add tests for empty result sets, invalid aggregate inputs, unexpected model return types.These cases can expose crashes or excessive work that the current six questions do not cover.
