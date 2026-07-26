import torch
import torch.nn as nn


class AdversarialLoss(nn.Module):
    """
    Adversarial loss.
    Implemented according to https://arxiv.org/abs/1711.10337
    """

    def __init__(self, type='nsgan', target_real_label=1.0, target_fake_label=0.0):
        """
        Available loss types: 'nsgan' | 'lsgan' | 'hinge'
        type: Which GAN loss type to use.
        target_real_label: Target label value for real images.
        target_fake_label: Target label value for generated images.
        """
        super(AdversarialLoss, self).__init__()
        self.type = type  # Loss type
        # Register labels as buffers so they are saved/loaded with the model
        self.register_buffer('real_label', torch.tensor(target_real_label))
        self.register_buffer('fake_label', torch.tensor(target_fake_label))

        # Initialize the loss function for the selected type
        if type == 'nsgan':
            self.criterion = nn.BCELoss()  # Binary cross-entropy (non-saturating GAN)
        elif type == 'lsgan':
            self.criterion = nn.MSELoss()  # Mean squared error (least-squares GAN)
        elif type == 'hinge':
            self.criterion = nn.ReLU()  # ReLU used for hinge loss

    def __call__(self, outputs, is_real, is_disc=None):
        """
        Compute the loss.
        outputs: Network outputs.
        is_real: True for real samples, False for generated samples.
        is_disc: Whether the discriminator is currently being optimized.
        """
        if self.type == 'hinge':
            # Hinge loss
            if is_disc:
                # Discriminator branch
                if is_real:
                    outputs = -outputs  # Flip sign for real samples
                # max(0, 1 - (real/fake) sample output)
                return self.criterion(1 + outputs).mean()
            else:
                # Generator: -min(0, -output) = max(0, output)
                return (-outputs).mean()
        else:
            # nsgan and lsgan losses
            labels = (self.real_label if is_real else self.fake_label).expand_as(
                outputs)
            # Compute loss between model outputs and target labels
            loss = self.criterion(outputs, labels)
            return loss
