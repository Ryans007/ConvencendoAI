from django.urls import path

from apps.review.views import ReviewSummaryView

urlpatterns = [
    path("review/summary/", ReviewSummaryView.as_view(), name="review-summary"),
]
