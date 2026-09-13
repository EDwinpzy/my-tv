-- Transactional production smoke test for protocol v2. Every mutation is rolled back.
begin;

do $smoke$
declare
  cards text[];
  card_one text;
  card_two text;
  device_a text := repeat('a', 64);
  device_b text := repeat('b', 64);
  device_c text := repeat('c', 64);
  first_result json;
  second_result json;
  third_result json;
  verify_result json;
  renew_result json;
  original_expiry timestamptz;
begin
  select array_agg(code order by code) into cards
    from (select code from public.licenses
          where plan = 'monthly' and activated_at is null and redeemed_at is null
          order by code limit 2) available;
  if coalesce(array_length(cards, 1), 0) <> 2 then
    raise exception 'smoke test requires two fresh monthly cards';
  end if;
  card_one := cards[1];
  card_two := cards[2];

  if (public.activate_code(card_one, device_a, null, null, null, null)->>'ret')::int <> 426 then
    raise exception 'legacy protocol was not rejected';
  end if;

  first_result := public.activate_code(card_one, device_a, null, 2, 'activate', null);
  second_result := public.activate_code(card_one, device_b, null, 2, 'activate', null);
  third_result := public.activate_code(card_one, device_c, null, 2, 'activate', null);
  if (first_result->>'ret')::int <> 0 or (second_result->>'ret')::int <> 0 then
    raise exception 'first or second activation failed';
  end if;
  if first_result->>'activatedAt' <> second_result->>'activatedAt'
     or first_result->>'expireAt' <> second_result->>'expireAt' then
    raise exception 'two devices received different membership dates';
  end if;
  if (third_result->>'ret')::int <> 402 then
    raise exception 'third device was not rejected';
  end if;

  verify_result := public.activate_code(card_one, device_a, null, 2, 'verify', null);
  if (verify_result->>'ret')::int <> 0 then
    raise exception 'bound-device verification failed';
  end if;

  original_expiry := (first_result->>'expireAt')::timestamptz;
  renew_result := public.activate_code(card_two, device_a, null, 2, 'renew', card_one);
  if (renew_result->>'ret')::int <> 0 or renew_result->>'licenseCode' <> card_one then
    raise exception 'renewal did not retain the canonical card';
  end if;
  if (renew_result->>'expireAt')::timestamptz <= original_expiry then
    raise exception 'renewal did not extend the unified expiry';
  end if;
  if not exists (select 1 from public.licenses where code = card_two
                 and redeemed_at is not null and redeemed_to = card_one) then
    raise exception 'renewal card was not marked redeemed';
  end if;
end;
$smoke$;

rollback;
