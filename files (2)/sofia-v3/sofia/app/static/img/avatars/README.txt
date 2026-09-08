Testimonial avatars
===================

Portrait images for the people quoted on the homepage.

The cards render a lettered circle wherever a photograph is missing, so
this folder can stay empty without breaking the layout. To add a face:

  1. Drop the image in here. Square, 160x160 or larger, JPG or WebP.
     The card crops to a 40px circle with object-fit: cover, so anything
     square lands correctly and anything else gets centre-cropped.
  2. Open app/testimonials.py and set that person's "avatar" field to
     the filename, for example "adaeze-nwosu.jpg".

Nothing else needs changing. Name files after the person so the mapping
stays obvious a year from now.
