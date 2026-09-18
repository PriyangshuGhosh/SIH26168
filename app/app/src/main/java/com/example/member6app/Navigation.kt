package com.example.member6app

import androidx.compose.runtime.Composable
import com.example.member6app.navigation.NavigationViewModel
import com.example.member6app.ui.NavigationScreen
import androidx.lifecycle.viewmodel.compose.viewModel

/**
 * MainNavigation — replaces the template nav3 boilerplate.
 * The app is single-screen (NavigationScreen handles all tabs internally).
 */
@Composable
fun MainNavigation(viewModel: NavigationViewModel = viewModel()) {
    NavigationScreen(viewModel = viewModel)
}
