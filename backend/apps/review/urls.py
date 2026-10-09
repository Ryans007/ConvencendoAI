from django.urls import path

from apps.review.views import ReviewItemDiscardView, ReviewSummaryView

urlpatterns = [
    path("review/summary/", ReviewSummaryView.as_view(), name="review-summary"),
    path(
        "review/items/<int:item_id>/discard/",
        ReviewItemDiscardView.as_view(),
        name="review-item-discard",
    ),
]
