ALTER TABLE public.sc03_orders DROP COLUMN status
ALTER TABLE public.sc03_orders DROP CONSTRAINT sc03_amount_positive
ALTER TABLE public.sc03_orders ALTER COLUMN amount TYPE text USING amount::text
