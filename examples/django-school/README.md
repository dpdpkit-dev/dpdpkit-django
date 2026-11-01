# django-school

A small ed-tech site wired to dpdpkit-django, showing a **child-account flow**: notice and consent, a guardian
consent step for learners under 18, `@requires_consent`, the preferences tags, erasure through
`PersonalDataRegistry` and the admin back-office.

```bash
pip install -e "../..[dev]"
python manage.py migrate
python manage.py createsuperuser        # staff users see the dpdpkit admin screens
python manage.py runserver
```

## The child flow

1. **Sign up** at `/signup/`. The date of birth decides whether the learner is a child (under the policy's
   `children.age_of_majority`, 18). A child must give a parent or guardian's name and email. The account is created
   with **no consent recorded**.
2. **Guardian link.** The site builds a signed link that expires (`GUARDIAN_LINK_MAX_AGE`, seven days) and stops
   working if the guardian's address changes. The demo prints it to the console and the sign-up page; a real site
   emails or texts it. Opening the link is the only verification here. Whether that meets the "verifiable consent"
   duty in the Act and Rules for your service is a question for your counsel; swap in a stronger check in
   `school/guardians.py` if it does not.
3. **Guardian chooses** at `/guardian/<token>/`. Nothing is pre-ticked. Choices are recorded under the child's
   principal with `source="guardian"` and the guardian's details in the event metadata. The same link lets the
   guardian withdraw later. `product_improvement` and `marketing` (see `ADULT_ONLY`) are never offered and are
   ignored if posted, because tracking and targeted marketing aimed at children are barred.
4. **Gate.** `/course/` uses `@requires_consent("learning")`, so the child is locked out (403) until the guardian
   grants it, and again if the guardian withdraws. A child cannot use `/privacy/preferences/`; adults make their own
   choices there with `{% dpdp_preferences %}`.
5. **Erasure.** `school/apps.py` registers `Learner` and `Progress` with the registry, so an erasure request or a
   retention run clears them (the registry is attached to the kit on the first request).

Authentication is Django's own; the signed-in user's id is the dpdpkit principal and staff users are admins.

## Tests

```bash
cd examples/django-school && DATABASE_NAME=:memory: pytest -q
```

The dpdpkit conformance suite against this app is tracked as DJ-09.
