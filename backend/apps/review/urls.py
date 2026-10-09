from django.urls import path

from apps.review.views import ReviewItemDiscardView, ReviewRoundView, ReviewSummaryView

urlpatterns = [
    path("review/summary/", ReviewSummaryView.as_view(), name="review-summary"),
    path("review/round/", ReviewRoundView.as_view(), name="review-round"),
    path(
        "review/items/<int:item_id>/discard/",
        ReviewItemDiscardView.as_view(),
        name="review-item-discard",
    ),
]
