# Copyright © 2023 Apple Inc.

import mlx.core as mx
from mlx.nn.layers.base import Module

from typing import Tuple


class LayerNorm(Module):
    r"""Applies layer normalization [1] on the inputs.

    Computes

    .. math::

        y = \frac{x - E[x]}{\sqrt{Var[x]} + \epsilon} \gamma + \beta,

    where :math:`\gamma` and :math:`\beta` are learned per feature dimension
    parameters initialized at 1 and 0 respectively.

    [1]: https://arxiv.org/abs/1607.06450

    Args:
        dims (int): The feature dimension of the input to normalize over
        eps (float): A small additive constant for numerical stability
        affine (bool): If True learn an affine transform to apply after the
            normalization
    """

    def __init__(self, dims: int, eps: float = 1e-5, affine: bool = True):
        super().__init__()
        if affine:
            self.bias = mx.zeros((dims,))
            self.weight = mx.ones((dims,))
        self.eps = eps
        self.dims = dims

    def _extra_repr(self):
        return f"{self.dims}, eps={self.eps}, affine={'weight' in self}"

    def __call__(self, x):
        means = mx.mean(x, axis=-1, keepdims=True)
        var = mx.var(x, axis=-1, keepdims=True)
        x = (x - means) * mx.rsqrt(var + self.eps)
        return (self.weight * x + self.bias) if "weight" in self else x


class RMSNorm(Module):
    r"""Applies Root Mean Square normalization [1] to the inputs.

    Computes

    ..  math::

        y = \frac{x}{\sqrt{E[x^2] + \epsilon}} \gamma

    where :math:`\gamma` is a learned per feature dimension parameter initialized at
    1.

    [1]: https://arxiv.org/abs/1910.07467

    Args:
        dims (int): The feature dimension of the input to normalize over
        eps (float): A small additive constant for numerical stability
    """

    def __init__(self, dims: int, eps: float = 1e-5):
        super().__init__()
        self.weight = mx.ones((dims,))
        self.eps = eps

    def _extra_repr(self):
        return f"{self.weight.shape[0]}, eps={self.eps}"

    def __call__(self, x):
        # S is 1/sqrt(N) where N is the size of the features of x and is used
        # to compute a numerically more stable RMS of x by multiplying with S
        # first and summing.
        #
        # This way we prefer underflow over overflow which is controlled with
        # the parameter epsilon anyway.
        S = 1 / x.shape[-1] ** 0.5

        n = (x * S).square().sum(axis=-1, keepdims=True)
        n = mx.rsqrt(n + self.eps)

        return self.weight * x * n


class GroupNorm(Module):
    r"""Applies Group Normalization [1] to the inputs.

    Computes the same normalization as layer norm, namely

    .. math::

        y = \frac{x - E[x]}{\sqrt{Var[x]} + \epsilon} \gamma + \beta,

    where :math:`\gamma` and :math:`\beta` are learned per feature dimension
    parameters initialized at 1 and 0 respectively. However, the mean and
    variance are computed over the spatial dimensions and each group of
    features. In particular, the input is split into num_groups accross the
    feature dimension.

    The feature dimension is assumed to be the last dimension and the dimensions
    that precede it (except the first) are considered the spatial dimensions.

    [1]: https://arxiv.org/abs/1803.08494

    Args:
        num_groups (int): Number of groups to separate the features into
        dims (int): The feature dimensions of the input to normalize over
        eps (float): A small additive constant for numerical stability
        affine (bool): If True learn an affine transform to apply after the
            normalization.
        pytorch_compatible (bool): If True perform the group normalization in
            the same order/grouping as PyTorch.
    """

    def __init__(
        self,
        num_groups: int,
        dims: int,
        eps: float = 1e-5,
        affine: bool = True,
        pytorch_compatible: bool = False,
    ):
        super().__init__()
        if affine:
            self.bias = mx.zeros((dims,))
            self.weight = mx.ones((dims,))
        self.num_groups = num_groups
        self.dims = dims
        self.eps = eps
        self.pytorch_compatible = pytorch_compatible

    def _extra_repr(self):
        return (
            f"{self.num_groups}, {self.dims}, eps={self.eps}, "
            f"affine={'weight' in self}, pytorch_compatible={self.pytorch_compatible}"
        )

    def _pytorch_compatible_group_norm(self, x):
        num_groups = self.num_groups
        batch, *rest, dims = x.shape

        # Split into groups
        x = x.reshape(batch, -1, num_groups, dims // num_groups)
        x = x.transpose(0, 1, 3, 2).reshape(batch, -1, num_groups)

        # Normalize
        means = mx.mean(x, axis=1, keepdims=True)
        var = mx.var(x, axis=1, keepdims=True)
        x = (x - means) * mx.rsqrt(var + self.eps)
        x = x.reshape(batch, -1, dims // num_groups, num_groups)
        x = x.transpose(0, 1, 3, 2).reshape(batch, *rest, dims)

        return x

    def _group_norm(self, x):
        num_groups = self.num_groups
        batch, *rest, dims = x.shape

        # Split into groups
        x = x.reshape(batch, -1, num_groups)

        # Normalize
        means = mx.mean(x, axis=1, keepdims=True)
        var = mx.var(x, axis=1, keepdims=True)
        x = (x - means) * mx.rsqrt(var + self.eps)
        x = x.reshape(batch, *rest, dims)

        return x

    def __call__(self, x):
        group_norm = (
            self._pytorch_compatible_group_norm
            if self.pytorch_compatible
            else self._group_norm
        )
        x = group_norm(x)
        return (self.weight * x + self.bias) if "weight" in self else x


import mlx.core as mx
from mlx.nn.layers.base import Module


class BatchNorm1d(Module):
    r"""Applies Batch Normalization [1] to the inputs.

    Computes

    .. math::

        y = \frac{x - E[x]}{\sqrt{Var[x]} + \epsilon} \gamma + \beta,

    where :math:`\gamma` and :math:`\beta` are learned per feature dimension
    parameters initialized at 1 and 0 respectively.

    [1]: https://arxiv.org/abs/1502.03167

    Args:
        num_features (int): The feature dimension of the input to normalize over.
        eps (float, optional): A small additive constant for numerical stability. Default is 1e-5.
        momentum (float, optional): The momentum for updating the running mean and variance. Default is 0.1.
        affine (bool, optional): If True, learn an affine transform to apply after the normalization. Default is True.

    Examples:
        >>> import mlx.core as mx
        >>> import mlx.nn as nn

        >>> # With Learnable Parameters
        >>> m = nn.BatchNorm1d(100)
        >>> # Without Learnable Parameters
        >>> m = nn.BatchNorm1d(4, affine=False)
        >>> input = mx.random.normal(20, 4)
        >>> output = m(input)

    """

    def __init__(
        self,
        num_features: int,
        eps: float = 1e-5,
        momentum: float = 0.1,
        affine: bool = True,
    ):
        super().__init__()
        if affine:
            self.bias = mx.zeros((num_features,))
            self.weight = mx.ones((num_features,))

        self.num_features = num_features
        self.eps = eps
        self.momentum = momentum
        self.running_mean = mx.zeros((num_features,))
        self.running_var = mx.ones((num_features,))

    def _extra_repr(self):
        return f"num_features={self.num_features}, eps={self.eps}, momentum={self.momentum}, affine={'weight' in self}"

    def _calc_stats(self, x: mx.array) -> Tuple[mx.array, mx.array]:
        """
        Calculate the mean and variance of the input tensor.

        Args:
            x (mx.array): Input tensor.

        Returns:
            tuple: Tuple containing mean and variance.
        """
        means = mx.mean(x, axis=0, keepdims=True)
        var = mx.var(x, axis=0, keepdims=True)
        self.running_mean = (
            self.momentum * self.running_mean + (1 - self.momentum) * means
        )
        self.running_var = self.momentum * self.running_var + (1 - self.momentum) * var
        return means, var

    def __call__(self, x: mx.array):
        """
        Forward pass of BatchNorm1d.

        Args:
            x (mx.array): Input tensor.

        Returns:
            mx.array: Output tensor.
        """
        if x.ndim != 2:
            raise ValueError("BatchNorm1d only supports 2D inputs")

        means, var = self.running_mean, self.running_var
        if self.training:
            means, var = self._calc_stats(x)
        x = (x - means) * mx.rsqrt(var + self.eps)
        return (self.weight * x + self.bias) if "weight" in self else x

# if __name__ == '__main__':
    
#     import mlx.core as mx
#     import mlx.nn as nn

#     # With Learnable Parameters
#     m = nn.BatchNorm1d(100)
#     # Without Learnable Parameters
#     m = nn.BatchNorm1d(4, affine=False)
#     input = mx.random.normal(20, 4)
#     output = m(input)
#     print(output)


import unittest
import mlx.core as mx
import mlx.nn as nn

class TestBatchNorm1d(unittest.TestCase):

    def test_forward_pass_training(self):
        # Test the forward pass during training
        num_features = 5
        batch_size = 10
        input_data = mx.random.normal(shape=(batch_size, num_features))
        bn_layer = BatchNorm1d(num_features)
        
        # Initial running mean and variance should be zeros and ones respectively
        self.assertTrue(mx.all(bn_layer.running_mean == mx.zeros((num_features,))))
        self.assertTrue(mx.all(bn_layer.running_var == mx.ones((num_features,))))
        
        # Perform a forward pass
        output = bn_layer(input_data)
        
        # Check that the running mean and variance have been updated
        self.assertFalse(mx.all(bn_layer.running_mean == mx.zeros((num_features,))))
        self.assertFalse(mx.all(bn_layer.running_var == mx.ones((num_features,))))
        
        # Check that the output shape matches the input shape
        self.assertEqual(output.shape, input_data.shape)

    def test_forward_pass_evaluation(self):
        # Test the forward pass during evaluation
        num_features = 5
        batch_size = 10
        input_data = mx.random.normal(shape=(batch_size, num_features))
        bn_layer = BatchNorm1d(num_features)
        
        # Set the layer to evaluation mode
        bn_layer.eval()
        
        # Initial running mean and variance should be zeros and ones respectively
        self.assertTrue(mx.all(bn_layer.running_mean == mx.zeros((num_features,))))
        self.assertTrue(mx.all(bn_layer.running_var == mx.ones((num_features,))))
        
        # Perform a forward pass
        output = bn_layer(input_data)
        
        # Running mean and variance should not be updated during evaluation
        self.assertTrue(mx.all(bn_layer.running_mean == mx.zeros((num_features,))))
        self.assertTrue(mx.all(bn_layer.running_var == mx.ones((num_features,))))
        
        # Check that the output shape matches the input shape
        self.assertEqual(output.shape, input_data.shape)

    def test_2d_input_shape(self):
        # Test if the layer raises an error for non-2D inputs
        num_features = 5
        batch_size = 10
        input_data = mx.random.normal(shape=(batch_size, num_features, 3))
        bn_layer = BatchNorm1d(num_features)
        
        with self.assertRaises(ValueError):
            output = bn_layer(input_data)

    def test_affine_false(self):
        # Test if the layer behaves correctly when affine is set to False
        num_features = 5
        batch_size = 10
        input_data = mx.random.normal(shape=(batch_size, num_features))
        bn_layer = BatchNorm1d(num_features, affine=False)
        
        output = bn_layer(input_data)
        
        # Check that the output shape matches the input shape
        self.assertEqual(output.shape, input_data.shape)
        
        # Check that the learned parameters (weight and bias) are not present
        self.assertFalse(hasattr(bn_layer, 'weight'))
        self.assertFalse(hasattr(bn_layer, 'bias'))

if __name__ == '__main__':
    unittest.main()
